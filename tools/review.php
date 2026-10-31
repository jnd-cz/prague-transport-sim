<?php
// Review verdicts on the web host (#136): tools/deploy.py uploads this as /review.php, behind the site's
// basic auth. GET ?f=NAME returns reviews/NAME.json; POST ?f=NAME merges the posted records into it:
// per finding the newer "t" wins (the rule of tools/reviews.py: change both). The page sends an
// X-Review header, which a cross-site form cannot: a post from another site gets no CORS answer.
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
$name = isset($_GET['f']) ? $_GET['f'] : '';
if (!preg_match('/^[a-z0-9_-]{1,64}$/', $name)) {
  http_response_code(400);
  exit('{"error":"name"}');
}
$dir = __DIR__ . '/reviews';
$path = "$dir/$name.json";
if ($_SERVER['REQUEST_METHOD'] === 'GET') {
  echo is_file($path) ? file_get_contents($path) : '{}';
  exit;
}
if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !isset($_SERVER['HTTP_X_REVIEW'])) {
  http_response_code(405);
  exit('{"error":"method"}');
}
$body = file_get_contents('php://input', false, null, 0, 2000001);
if ($body === false || strlen($body) > 2000000) {
  http_response_code(413);
  exit('{"error":"size"}');
}
$new = json_decode($body, true);
if (!is_array($new) || !isset($new['items']) || !is_array($new['items'])) {
  http_response_code(400);
  exit('{"error":"json"}');
}
if (!is_dir($dir)) mkdir($dir, 0750);
$fh = fopen($path, 'c+');
if (!$fh || !flock($fh, LOCK_EX)) {
  http_response_code(500);
  exit('{"error":"lock"}');
}
$cur = json_decode(stream_get_contents($fh), true);
if (!is_array($cur)) $cur = array();
$items = isset($cur['items']) && is_array($cur['items']) ? $cur['items'] : array();
foreach ($new['items'] as $k => $v) {
  if (!is_string($k) || !is_array($v)) continue;
  $t = isset($v['t']) ? $v['t'] : 0;
  if (!isset($items[$k]) || $t >= (isset($items[$k]['t']) ? $items[$k]['t'] : 0)) $items[$k] = $v;
}
$meta = array_merge(isset($cur['meta']) && is_array($cur['meta']) ? $cur['meta'] : array(),
                    isset($new['meta']) && is_array($new['meta']) ? $new['meta'] : array());
$out = json_encode(array('meta' => (object) $meta, 'items' => (object) $items), JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT);
ftruncate($fh, 0);
rewind($fh);
fwrite($fh, $out);
fflush($fh);
flock($fh, LOCK_UN);
fclose($fh);
echo json_encode(array('ok' => true, 'items' => count($items)));
