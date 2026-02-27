# Why the Engine Is Not Written in Rust (Yet)

## TL;DR

The installed Rust toolchain (**1.83.0**, Nov 2024) is too old to compile
the transitive dependency tree required by the ZeroMQ, UUID and other
crates used in this project. The blocker is the `getrandom v0.4.1` crate
which requires the **`edition2024`** Cargo feature that was only
stabilised in **Rust 1.85+** (Feb 2025).

---

## Detailed Root Cause

| Component | Version |
|---|---|
| Installed `rustc` | 1.83.0 (90b35a623 2024-11-26) |
| Installed `cargo` | 1.83.0 (5ffbef321 2024-10-29) |
| Required minimum | **1.85.0** |

When running `cargo check` in `Engine/`, Cargo resolves the dependency
graph and pulls in:

```
getrandom v0.4.1
├── required by uuid (via getrandom feature)
├── required by zeromq
└── ...
```

`getrandom 0.4.1`'s `Cargo.toml` declares:

```toml
cargo-features = ["edition2024"]
edition = "2024"
```

This feature **does not exist** in Cargo 1.83 and cannot be used until
Cargo 1.85. The error is:

```
error: failed to parse manifest at
  .../registry/src/.../getrandom-0.4.1/Cargo.toml

Caused by:
  the cargo feature `edition2024` requires a nightly version of
  Cargo, but this is the `stable` channel
  ...
  this Cargo does not support nightly features, but if you
  switch to nightly channel you can add
  `cargo-features = ["edition2024"]` to enable this feature.
```

## What We Tried

1. **Downgrading `zeromq`** from `0.4` to `0.3` — still transitively
   pulls `getrandom >= 0.4` via other deps.
2. **Pinning `uuid`** to `>=1.0, <1.12` — same result; the Cargo
   resolver still selects `getrandom 0.4.x`.
3. **`rustup update stable`** — download stalled at ~50 KB/s
   (20.7 MiB), reaching only ~29 % before timing out. Likely a network
   issue at the hackathon venue.

None of these approaches resolved the build.

## Resolution — C++ Port

Rather than blocking on a slow toolchain download during a
time-constrained hackathon, the math engine has been ported to **C++20**
with equivalent functionality:

| Rust concept | C++ replacement |
|---|---|
| `DashMap<CompositeKey, NormalizedMarket>` | `std::unordered_map` + `std::shared_mutex` |
| `serde` + `serde_json` | `nlohmann/json` |
| `tokio` async tasks | `std::thread` |
| `zeromq` crate | `cppzmq` (or compile-time stub) |
| `tracing` | `spdlog` |
| `rust_decimal` | `double` (sufficient for basis-point math) |

The original Rust sources (`Engine/src/types.rs`, `matcher.rs`,
`main.rs`, `Cargo.toml`) are preserved in the repo for a future port
once the toolchain is updated.

## Future Fix

Once a Rust 1.85+ toolchain is available:

```bash
rustup update stable
cd Engine
cargo check   # should succeed
cargo build --release
```

Then swap the C++ binary back to the Rust binary in the deployment
pipeline.
