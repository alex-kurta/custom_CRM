<?php

if ($argc !== 3) {
    fwrite(STDERR, "Usage: php merge-config.php <live-config.php> <overrides.php>\n");
    exit(1);
}

$livePath = $argv[1];
$overridePath = $argv[2];

if (!is_file($livePath) || !is_readable($livePath)) {
    fwrite(STDERR, "Live config not readable: {$livePath}\n");
    exit(1);
}

if (!is_file($overridePath) || !is_readable($overridePath)) {
    fwrite(STDERR, "Override config not readable: {$overridePath}\n");
    exit(1);
}

$live = include $livePath;
$overrides = include $overridePath;

if (!is_array($live)) {
    fwrite(STDERR, "Live config did not return an array.\n");
    exit(1);
}

if (!is_array($overrides)) {
    fwrite(STDERR, "Override config did not return an array.\n");
    exit(1);
}

$added = [];

foreach ($overrides as $key => $value) {
    if (!array_key_exists($key, $live)) {
        $live[$key] = $value;
        $added[] = $key;
    }
}

$export = "<?php\nreturn " . var_export($live, true) . ";\n";

if (file_put_contents($livePath, $export) === false) {
    fwrite(STDERR, "Failed writing merged config.\n");
    exit(1);
}

fwrite(STDOUT, empty($added) ? "Added: none\n" : "Added: " . implode(', ', $added) . "\n");
