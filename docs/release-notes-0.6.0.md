# Release notes 0.6.0

- New losses job and Losses tab: efficiency over speed and torque level, loss split, B(t) in a picked iron element.
- The drive search now continues past the aligned position (tail), and the off grid is a superset of the old one.
  Both change evaluations and search rankings.
- The winding temperature is a requirements input, default 120 degC (was a fixed 100 degC).
- Evaluations made before 0.6.0 must be re-evaluated before running losses (the route answers 409 otherwise).
- Cached maps rebuild once, because the version is part of the provenance.
- 0.6.0 is not yet in `VALIDATED_VERSIONS`.
- The bench goldens still pin 0.5.0 and are to be regenerated.
