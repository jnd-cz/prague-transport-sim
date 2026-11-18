<?php
// SPDX-License-Identifier: AGPL-3.0-or-later
// Vehicle packages submitted for review (#580): tools/deploy.py uploads this as /submit.php on every target. It only
// takes submissions in: a multipart POST from the Vehicles... page (src/packagesMenu.js) with `meta` (JSON: the
// game's check of each package in it, the author's optional contact and note, whether the project may host it) and
// either `pack` (the .zip) or meta.url (its address on the author's host). Stored as submissions/<id>/ (meta.json,
// pack.zip), denied to the web; tools/deploy.py --pull moves them off over FTPS and tools/submissions.py reviews
// them. No IP address is stored. Its checks and caps are tools/submissions.py's (tools/serve.py applies them
// locally): change both. The user, 2026-11-15: "these sound like reasonable limits for now".
// The host's PHP must take a 64 MB upload (upload_max_filesize, post_max_size).
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
const MAX_META = 65536;
const MAX_CONTACT = 200;
const MAX_NOTE = 2000;
const MAX_URL = 500;
const MAX_ENTRIES = 1000;
const PER_HOUR = 10;              // submissions from everyone together
const MAX_KEPT = 200;             // submissions kept until a pull
const MAX_BYTES = 2000000000;     // bytes kept until a pull

function fail($code, $what) {
  http_response_code($code);
  exit(json_encode(array('error' => $what)));
}

// what a package may hold: the game's own rules (src/packageRules.json, deployed with the game)
$rules = json_decode(@file_get_contents(__DIR__ . '/src/packageRules.json'), true);
if (!is_array($rules)) fail(500, 'rules');
$cap = $rules['caps']['package'];

// (the page sends X-Submit, which a cross-site form cannot: a post from another site gets no CORS answer)
if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !isset($_SERVER['HTTP_X_SUBMIT'])) fail(405, 'method');
if (empty($_POST) && empty($_FILES)) fail(413, 'size');   // (PHP drops a body over post_max_size)
$raw = isset($_POST['meta']) ? $_POST['meta'] : null;
if (!is_string($raw) || strlen($raw) > MAX_META) fail(400, 'meta');
$meta = json_decode($raw, true);
if (!is_array($meta) || array_keys($meta) === range(0, count($meta) - 1)) fail(400, 'meta');
foreach (array('contact' => MAX_CONTACT, 'note' => MAX_NOTE) as $k => $max) {
  if (isset($meta[$k]) && (!is_string($meta[$k]) || mb_strlen($meta[$k], 'UTF-8') > $max)) fail(400, $k);
}
if (!isset($meta['host']) || !is_bool($meta['host'])) fail(400, 'host');
if (!isset($meta['licence']) || $meta['licence'] !== true) fail(400, 'licence');
$url = isset($meta['url']) ? $meta['url'] : null;
if ($url !== null && !(is_string($url) && strlen($url) <= MAX_URL
    && preg_match('~^https://[^\s"\'<>]+?(\.zip|/package\.json)(\?[^\s"\'<>]*)?$~', $url))) fail(400, 'url');
$file = isset($_FILES['pack']) ? $_FILES['pack'] : null;
if ($file && $file['error'] === UPLOAD_ERR_NO_FILE) $file = null;
if (($url === null) === ($file === null)) fail(400, 'pack or url');
if (!isset($meta['packages']) || !is_array($meta['packages']) || !count($meta['packages']) || count($meta['packages']) > 50) fail(400, 'packages');
// (each names itself as the game's check passes it: the id and version become a file's name at the review)
foreach ($meta['packages'] as $p) {
  if (!is_array($p) || !isset($p['id'], $p['version']) || !is_string($p['id']) || !is_string($p['version'])
      || !preg_match('~' . $rules['id'] . '~D', $p['id']) || !preg_match('/^\d+\.\d+\.\d+$/D', $p['version'])) fail(400, 'packages');
}

// the archive: a zip within the package cap, each entry of a type the game takes (its central directory read)
$pack = null;
if ($file) {
  if ($file['error'] === UPLOAD_ERR_INI_SIZE || $file['error'] === UPLOAD_ERR_FORM_SIZE || $file['size'] > $cap) fail(413, 'size');
  if ($file['error'] !== UPLOAD_ERR_OK || !is_uploaded_file($file['tmp_name'])) fail(400, 'pack');
  $pack = file_get_contents($file['tmp_name']);
  if (strlen($pack) > $cap) fail(413, 'size');
  $why = zip_problem($pack, $rules['types']);
  if ($why) fail(400, $why);
}

function zip_problem($d, $types) {
  if (substr($d, 0, 4) !== "PK\x03\x04") return 'zip';
  $tail = substr($d, -min(strlen($d), 65557));   // (the end record, within a comment's length of the end)
  $r = strrpos($tail, "PK\x05\x06");
  if ($r === false) return 'zip';
  $at = strlen($d) - strlen($tail) + $r;
  if ($at + 22 > strlen($d)) return 'zip';
  $e = unpack('vcount/Vsize/Vstart', substr($d, $at + 10, 10));
  if ($e['count'] > MAX_ENTRIES || $e['start'] + $e['size'] > $at) return 'zip';
  $p = $e['start'];
  for ($i = 0; $i < $e['count']; $i++) {
    if (substr($d, $p, 4) !== "PK\x01\x02") return 'zip';
    $h = unpack('vn/vx/vc', substr($d, $p + 28, 6));
    $name = substr($d, $p + 46, $h['n']);
    $p += 46 + $h['n'] + $h['x'] + $h['c'];
    if (substr($name, -1) === '/') continue;
    if ($name === '' || $name[0] === '/' || strpos($name, '\\') !== false || in_array('..', explode('/', $name), true)) return 'path';
    $base = basename($name);
    $ext = strpos($base, '.') === false ? '' : strtolower(substr($base, strrpos($base, '.') + 1));
    if (!isset($types[$ext])) return 'type';
  }
  return null;
}

$dir = __DIR__ . '/submissions';
if (!is_dir($dir)) mkdir($dir, 0750);
$lock = fopen("$dir/.lock", 'c');
if (!$lock || !flock($lock, LOCK_EX)) fail(500, 'lock');
$n = 0; $bytes = 0; $recent = 0; $now = time();
foreach (scandir($dir) as $f) {
  if (!preg_match('/^sub-\d{8}-\d{6}-[0-9a-f]{8}$/', $f)) continue;
  $n++;
  foreach (array('meta.json', 'pack.zip') as $g) if (is_file("$dir/$f/$g")) $bytes += filesize("$dir/$f/$g");
  if (filemtime("$dir/$f") > $now - 3600) $recent++;
}
if ($recent >= PER_HOUR) fail(429, 'busy');
if ($n >= MAX_KEPT || $bytes + strlen($raw) + ($pack === null ? 0 : strlen($pack)) > MAX_BYTES) fail(507, 'full');

$id = 'sub-' . gmdate('Ymd-His') . '-' . bin2hex(random_bytes(4));
$meta['id'] = $id;
$meta['received'] = gmdate('c');
$out = json_encode($meta, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
if ($out === false) fail(400, 'meta');
// (written whole: a folder made beside it, then renamed; a pull never sees half a submission)
$tmp = "$dir/$id.tmp";
if (!mkdir($tmp, 0750) || file_put_contents("$tmp/meta.json", $out) === false
    || ($pack !== null && file_put_contents("$tmp/pack.zip", $pack) === false) || !rename($tmp, "$dir/$id")) fail(500, 'write');
flock($lock, LOCK_UN);
fclose($lock);
echo json_encode(array('ok' => true, 'id' => $id));
