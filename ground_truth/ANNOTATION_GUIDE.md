# PreFlight Annotation Guide (AI-assisted concordance)

**Status:** AI-assisted concordance. This is **not** human inter-annotator agreement.

## Sample

- 30 evidence links, stratified across PCF, entity, typelist, template, Gosu, and tests.
- 20 findings from the labelled finding corpus.
- 12 demo mappings.

## Protocol

1. Two AI passes label each item independently, blind to `rules/` and to the tool output.
2. A disagreement is adjudicated against the cited public source or the fixture source line.
3. Cohen's kappa is reported. If kappa < 0.60, the sample is relabelled and the limitation is reported.
4. The reference target is authored in a separate blind pass with neutral descriptions, then sealed by hash.
5. If the same agent authored both the rules and the reference target, the result is labelled
   "internally authored, not independent". This build is internally authored and does not claim
   independence or blindness.

## Limits

- No human annotators were available in the build window.
- The holdout is a naming-shift holdout from the same generator, not a distribution shift.
- Metrics are demonstration evidence on synthetic fixtures, not a benchmark.
