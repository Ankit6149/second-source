# G3 test fixtures — origin labels (do not relabel)

- `valid_candidate.json` — **trusted-test-fixture**, hand-written by the
  product team to exercise the validator, interpreter, and verifier wiring.
  It is NOT Muse output and must never be presented as a generated candidate.
  Its rules were transcribed from observed owned-fixture behavior during
  development; the independent check that matters is the sealed verifier
  comparison, not this file's provenance.
