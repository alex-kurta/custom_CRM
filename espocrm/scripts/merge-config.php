<?php

if ($argc < 3 || $argc > 4) {
    fwrite(STDERR, "Usage: php merge-config.php <live-config.php> <overrides.php> [overwrite-keys-csv]\n");
    exit(1);
}

$livePath = $argv[1];
$overridePath = $argv[2];
$overwriteKeys = $argc === 4
    ? array_values(array_filter(array_map('trim', explode(',', $argv[3]))))
    : [];

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
    $exists = array_key_exists($key, $live);
    $overwrite = in_array($key, $overwriteKeys, true);

    if (!$exists || $overwrite) {
        $live[$key] = $value;
        $added[] = $exists ? "{$key} (overwritten)" : $key;
    }
}

$export = "<?php\nreturn " . var_export($live, true) . ";\n";

if (file_put_contents($livePath, $export) === false) {
    fwrite(STDERR, "Failed writing merged config.\n");
    exit(1);
}

fwrite(STDOUT, empty($added) ? "Added: none\n" : "Added: " . implode(', ', $added) . "\n");
