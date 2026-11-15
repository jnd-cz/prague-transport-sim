<?php
// SPDX-License-Identifier: AGPL-3.0-or-later
// Player feedback on the web host (#350): tools/deploy.py uploads this as /feedback.php on every target. It only
// takes notes in: POST a JSON note (src/report.js), stored as feedback/<id>.json under an id made here. Nothing
// is read back over HTTP (feedback/ is denied to the web); tools/deploy.py --pull moves the notes off the host
// over FTPS. The caps below are the protection of a site without a login (the user, 2026-11-10: "reasonable
// limits for note size, screenshot attaching allowed, number of stored records"); no IP address is stored.
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
const MAX_BODY = 2000000;      // bytes of one post: a 1280 px JPEG screenshot in base64 is ~0.2-0.6 MB
const MAX_NOTE = 5000;         // characters of the note
const MAX_FILES = 3000;        // notes kept until a pull moves them off
const MAX_BYTES = 500000000;   // bytes kept until a pull
const MAX_PER_MINUTE = 20;     // notes from everyone together

function fail($code, $what) {
  http_response_code($code);
  exit(json_encode(array('error' => $what)));
}

// (the page sends X-Feedback, which a cross-site form cannot: a post from another site gets no CORS answer)
if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !isset($_SERVER['HTTP_X_FEEDBACK'])) fail(405, 'method');
$body = file_get_contents('php://input', false, null, 0, MAX_BODY + 1);
if ($body === false || strlen($body) > MAX_BODY) fail(413, 'size');
$rec = json_decode($body, true);
if (!is_array($rec) || array_keys($rec) === range(0, count($rec) - 1)) fail(400, 'json');
if (!isset($rec['note']) || !is_string($rec['note']) || mb_strlen($rec['note'], 'UTF-8') > MAX_NOTE) fail(400, 'note');
if (isset($rec['shot']) && $rec['shot'] !== null
    && (!is_string($rec['shot']) || strncmp($rec['shot'], 'data:image/jpeg;base64,', 23) !== 0)) fail(400, 'shot');

$dir = __DIR__ . '/feedback';
if (!is_dir($dir)) mkdir($dir, 0750);
$lock = fopen("$dir/.lock", 'c');
if (!$lock || !flock($lock, LOCK_EX)) fail(500, 'lock');
$n = 0; $bytes = 0; $recent = 0; $now = time();
foreach (scandir($dir) as $f) {
  if (substr($f, -5) !== '.json') continue;
  $n++;
  $bytes += filesize("$dir/$f");
  if (filemtime("$dir/$f") > $now - 60) $recent++;
}
if ($recent >= MAX_PER_MINUTE) fail(429, 'busy');
if ($n >= MAX_FILES || $bytes + strlen($body) > MAX_BYTES) fail(507, 'full');

$id = 'fb-' . gmdate('Ymd-His') . '-' . bin2hex(random_bytes(4));
$rec['id'] = $id;
$rec['received'] = gmdate('c');
$out = json_encode($rec, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
if ($out === false) fail(400, 'json');
// (written whole: a pull never sees half a note)
if (file_put_contents("$dir/$id.tmp", $out) === false || !rename("$dir/$id.tmp", "$dir/$id.json")) fail(500, 'write');
flock($lock, LOCK_UN);
fclose($lock);
echo json_encode(array('ok' => true, 'id' => $id));
