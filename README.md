# Salvo

An asynchronous request dispatcher for SMS-sending APIs. Salvo distributes
requests to a target phone number across multiple endpoints using weighted
selection, tracks per-endpoint capacity and failures, and adapts its routing at
runtime through temporary jails and permanent removal.

---

## What Salvo Does

Given an endpoint configuration file and a target context, such as a phone
number to inject into each request, Salvo starts multiple asynchronous workers
that continuously:

1. Request the next API call from the pool.
2. Send the request using `aiohttp`.
3. Report the result back to the pool.
4. Allow the pool to update the endpoint's weight, failure state, or jail
   status.

Salvo is designed to deliver a high volume of SMS/OTP requests to a single
target number by distributing the load across many endpoints. The pool
prioritizes endpoints by weight, jails misbehaving ones, and permanently removes
endpoints that fail repeatedly.

---

## Features

* **Asynchronous execution** using `aiohttp` with configurable worker
  concurrency.
* **Weighted endpoint selection** backed by a Fenwick Tree, providing O(log n)
  selection and updates.
* **Limited and Unlimited execution modes** with different endpoint lifecycle
  and stopping behavior.
* **Automatic failure handling** through strikes, temporary jails, and permanent
  endpoint removal.
* **Live capacity tracking** that reduces endpoint weight as capacity is
  consumed.
* **Proxy support** with optional fallback to a direct connection after repeated
  failures.
* **Randomized User-Agent** assignment per worker using `fake-useragent`.
* **Structured console output** with severity, event, and response tags.
* **Deferred verdict processing** that reports the previous request while
  selecting the next request.
* **Non-blocking background logging** with a bounded queue and dropped-log
  tracking.
* **ETag-based endpoint synchronization** with validation and atomic file
  replacement.
* **Command history** with automatic trimming at 5 MiB.
* **Automatic management command discovery** for modules exposing a `COMMAND`
  callable in the `tools/` package.

---

## Requirements

* Python **3.11 or newer**
* Linux, macOS, or Windows
* Outbound network access

---

## Installation

### 1. Clone and enter the repository

```bash
git clone https://github.com/TheBitGlitch/salvo.git
cd salvo
```

### 2. Install Salvo

```bash
pip install -e .
```

The editable install keeps the `salvo` command linked to your working copy,
so changes to the source code are reflected without reinstalling the package.

If you want to install Salvo into the active Python environment without an
editable install, use `pip install .`. Alternatively, use
`pip install --user .` to install it only for your user account without
touching system packages.

To install the test tooling as well:

```bash
pip install -e ".[test]"
```

After installation, the `salvo` command is available on your `PATH`.

### 3. Download the endpoint configuration

```bash
salvo manage sync-endpoints
```

This downloads `endpoints.json` into the platform-specific user data directory
and stores its ETag in the cache. Subsequent syncs use `If-None-Match` to avoid
redundant downloads. Use `--force` to bypass the ETag, or `--source <URL>` to
point at a different remote.

---

## Usage

### Basic run

```bash
salvo run -t 09123456789
```

The target phone number accepts supported Iranian formats and is normalized
before being passed to the execution layer.

### Option reference

```text
salvo run
  -t, --target         Target phone number (required).
  -m, --mode           Execution mode: "limited" (default) or "unlimited".
  -l, --limit          Stop after N successful requests. Limited mode only.
  -c, --concurrency    Maximum number of concurrent workers. Default: 6.
  -p, --proxy          HTTP/HTTPS proxy URL.
      --endpoints      Path to the endpoint configuration JSON.
      --fail-tolerance Maximum consecutive failures before stopping.
                       Default: 6 in limited mode.
      --timeout        Per-request timeout in seconds. Default: 5.
      --fallback       Fall back to a direct connection after repeated proxy
                       failures. Limited mode only.
      --ssl            Enable SSL certificate verification. Default: off.
```

### Management commands

```bash
salvo manage sync-endpoints            # Download/refresh endpoints.json
salvo manage sync-endpoints --force    # Skip the ETag check
salvo manage clear-cache               # Remove the cache directory
salvo manage history                   # Show the last 20 invocations
salvo manage history -n 50             # Show the last 50
salvo manage history --clear           # Wipe the history file
```

The `manage` application uses runtime module discovery: any module under
`tools/` that exposes a callable named `COMMAND` is registered as a management
subcommand, with underscores converted to hyphens.

### Example output

Salvo uses ANSI escape codes to provide structured and colorized console
output. The example below is shown without colors for readability.

```text
17:38:26 [NOTICE] Mission started. <target: 9123456789, mode: limited, limit: None, concurrency: 6, proxy: http://192.0.2.10:8080, endpoints: C:\Users\User\AppData\Local\salvo\salvo\endpoints.json, fail_tolerance: 6, timeout: 5, fallback: True, ssl: False>
17:38:26 [NOTICE] All 6 workers are running.
17:38:27 [01] [SUCCESS] example.com <status_code: 200>
17:38:27 [02] [SUCCESS] sample.org <status_code: 200>
17:38:28 [03] [FAILURE] alpha.net <status_code: 0, error: ClientProxyConnectionError>
17:38:29 [04] [FAILURE] beta.io <status_code: 0, error: ClientProxyConnectionError>
17:38:29 [05] [FAILURE] gamma.dev <status_code: 0, error: ClientProxyConnectionError>
17:38:30 [06] [FAILURE] example.com <status_code: 0, error: ClientProxyConnectionError>
17:38:30 [07] [FAILURE] beta.io <status_code: 0, error: ClientProxyConnectionError>
17:38:31 [08] [FAILURE] sample.org <status_code: 0, error: ClientProxyConnectionError>
17:38:31 [CRITICAL] Consecutive failure tolerance reached (6). Connection reliability has been compromised.
17:38:31 [NOTICE] [FALLBACK] Proxy http://192.0.2.10:8080 failed 6 times. Falling back to direct connection.
17:38:32 [09] [SUCCESS] alpha.net <status_code: 200>
17:38:33 [10] [SUCCESS] beta.io <status_code: 200>
17:38:34 [11] [SUCCESS] sample.org <status_code: 200>
17:38:35 [12] [FAILURE] example.com <status_code: 429>
17:38:35 [13] [FAILURE] example.com <status_code: 429>
17:38:36 [14] [FAILURE] example.com <status_code: 429>
17:38:36 [NOTICE] [JAILED] API `example.com` jailed for 20.0s.
17:38:37 [15] [SUCCESS] alpha.net <status_code: 200>
17:38:38 [16] [SUCCESS] beta.io <status_code: 200>
17:38:40 [17] [SUCCESS] sample.org <status_code: 200>
17:38:42 [18] [SUCCESS] alpha.net <status_code: 200>
17:38:44 [19] [SUCCESS] beta.io <status_code: 200>
17:38:46 [20] [SUCCESS] sample.org <status_code: 200>
17:38:48 [21] [SUCCESS] alpha.net <status_code: 200>
17:38:50 [22] [SUCCESS] beta.io <status_code: 200>
17:38:52 [23] [SUCCESS] sample.org <status_code: 200>
17:38:54 [24] [SUCCESS] alpha.net <status_code: 200>
17:38:56 [NOTICE] [FREED] API `example.com` freed from jail.
17:38:57 [25] [FAILURE] example.com <status_code: 429>
17:38:58 [26] [FAILURE] example.com <status_code: 429>
17:38:59 [27] [FAILURE] example.com <status_code: 429>
17:38:59 [NOTICE] [PURGED] API `example.com` permanently removed after second jail.
17:39:00 [28] [SUCCESS] sample.org <status_code: 200>
17:39:01 [29] [SUCCESS] alpha.net <status_code: 200>
17:39:02 [NOTICE] Mission completed.
17:39:02 [SUMMARY] Time: 36.0s | Total: 29 | Success: 17 | Failure: 12 | Success Rate: 58.6% <dropped_logs: 0>
```

---

## Execution Modes

### Limited (default)

Limited mode is the default execution mode. The pool enforces endpoint capacity,
tracks failures, and controls the lifecycle of each endpoint.

* Initial endpoint weight is calculated as `capacity × ticket`, where both
  values are read from the endpoint configuration. `ticket` reflects the
  endpoint's priority — see
  [salvo-endpoints](https://github.com/TheBitGlitch/salvo-endpoints) for how
  it is computed.
* Each selection consumes one unit of endpoint capacity.
* When capacity reaches zero, the endpoint weight is set to zero and the
  endpoint is marked as removed.
* Consecutive failures accumulate strikes.
* On the third consecutive strike, the endpoint is jailed for 20 seconds.
* A jailed endpoint has its weight set to zero and is excluded from sampling.
* If a previously jailed endpoint reaches the strike limit again after being
  released, it is permanently purged.
* A successful request clears the endpoint's strikes and jail state.
* Execution stops when either `--limit` successful requests are reached or
  `--fail-tolerance` consecutive failures occur.

### Unlimited

Unlimited mode strips away all endpoint lifecycle management. Every endpoint is
assigned a weight of `1`, so all endpoints have an equal chance of being
selected.

* No capacity consumption.
* No strikes, jails, or purges.
* Failed endpoints are never retired, so the success rate drops over time as
  broken endpoints keep getting selected.
* Significantly faster than Limited, since there is no endpoint lifecycle
  bookkeeping overhead.
* `--limit`, `--fail-tolerance`, and `--fallback` are not allowed.

Use Unlimited when you want raw throughput and already know the endpoints are
healthy. Use Limited when you need the pool to adapt to endpoint health.

---

## Project Structure

```text
.
├── cli/                          # Cyclopts-based CLI layer
│   ├── __init__.py
│   ├── app.py                    # Top-level `salvo` application
│   ├── sub_apps.py               # `run` and auto-discovered `manage` commands
│   ├── converters.py             # CLI argument converters
│   ├── validators.py             # CLI argument validators
│   ├── variants.py               # CLI execution-mode variants
│   ├── regex_patterns.py         # Compiled regular expressions
│   ├── exceptions.py             # CLI validation exceptions
│   └── helpers.py                # CLI helper utilities
│
├── kernel/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── factory.py            # Builds API slots from endpoint config
│   │   ├── models.py             # API data models
│   │   ├── validator.py          # Endpoint schema validation
│   │   └── exceptions.py         # API exceptions
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── engine.py             # Async execution lifecycle and workers
│   │   ├── api_pool.py           # Weighted pool and endpoint state
│   │   └── session_tracker.py    # Session statistics and stop conditions
│   │
│   └── libs/
│       ├── __init__.py
│       ├── printer/
│       │   ├── __init__.py
│       │   ├── color.py          # ANSI color definitions
│       │   ├── console.py        # Console output and async logger
│       │   └── tags.py           # Severity and response tags
│       │
│       └── structures/
│           ├── __init__.py
│           └── fenwick_tree.py   # Fenwick Tree implementation
│
├── tools/                        # Auxiliary application operations
│   ├── __init__.py
│   ├── sync_endpoints.py         # Endpoint configuration synchronization
│   ├── clear_cache.py            # Cache cleanup
│   └── history.py                # Command history
│
├── tests/                        # pytest suite
├── default_path.py               # Platform-specific data and cache paths
├── salvo.py                      # Application entry point
└── pyproject.toml                # Project metadata and packaging
```

---

## Testing

The project includes a `pytest` suite under `tests/`, covering core components
and other critical application behavior. `pytest-asyncio` is used for
asynchronous tests.

```bash
pip install -e ".[test]"
pytest
```

---

## Dependencies

### Runtime

* `aiohttp` — Asynchronous HTTP client.
* `cyclopts` — Command-line interface framework.
* `fake-useragent` — User-Agent generation.
* `platformdirs` — Cross-platform data and cache directory resolution.

### Testing

* `pytest` — Test framework.
* `pytest-asyncio` — Async test support for pytest.

---

## Repositories

* Source Code: [salvo](https://github.com/TheBitGlitch/salvo)
* Endpoints: [salvo-endpoints](https://github.com/TheBitGlitch/salvo-endpoints)

---

## Disclaimer

This software is provided as-is. The author assumes no liability for misuse,
damage, or legal consequences arising from its use.

Users are responsible for complying with all applicable laws, regulations,
terms of service, and obtaining appropriate authorization before sending
requests to any service.

---

## License

Salvo is released under the [MIT License](LICENSE).

---

## Author

Developed by [@TheBitGlitch](https://github.com/TheBitGlitch).
