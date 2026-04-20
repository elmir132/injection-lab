# Honesty checklist

Before publishing a result, demo, or portfolio claim:

- [ ] State the exact prompt, model, provider, and fixture version used; do not publish the
  prompt or raw transcripts if they contain private material.
- [ ] Say that the supplied prompt was augmented with a synthetic canary.
- [ ] Report the number of fixtures and the lexical scoring rules. Keep `inconclusive` and
  provider errors visible instead of counting them as passes.
- [ ] Call a result a small fixture evaluation, not a benchmark, proof, certification, or
  general model-safety score.
- [ ] Separate offline mock results from real-model results. Mock results validate the
  harness plumbing only.
- [ ] Disclose that tool-output hijacking is simulated as text and that no actual tools
  were invoked.
- [ ] Never claim no data left the machine for an OpenAI run. The supplied prompt and
  fixtures are sent to the provider; check current provider terms before sending sensitive
  material.
- [ ] Do not include API keys, private prompts, canaries, or unreviewed transcripts in
  committed files or screenshots.
- [ ] Record model/version and date for real runs; results can vary across model versions
  and sampling.
- [ ] Explain known blind spots: lexical indicators, possible false positives, paraphrase
  misses, and the small hand-written suite.

