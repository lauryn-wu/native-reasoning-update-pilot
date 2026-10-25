# Third-party sources

The problem revisions and corrections used here come from the [Update benchmark](https://huggingface.co/datasets/dynamic-lm/update-interrupt-benchmark), released with [Are Large Reasoning Models Interruptible?](https://arxiv.org/html/2510.11713v3) and the [interrupt-lrm repository](https://github.com/dynamic-lm/interrupt-lrm).

The pinned update dataset and code declare Apache-2.0. A copy of the upstream license is preserved in [provenance/UPSTREAM_APACHE_LICENSE.txt](provenance/UPSTREAM_APACHE_LICENSE.txt). Exact revisions, file hashes, and source URLs are in [provenance/source_lock.json](provenance/source_lock.json).

This repository adds the completed-answer correction protocol, API retention comparison, independent reference construction, grading harness, and result summaries. The released source statements and corrections are retained in the reviewed source-pair records and frozen manifests. The repository includes 64 reviewed coding pairs and 22 reviewed math pairs, not just identifiers and hashes. The executed pilot used four of those pairs.

The original problems come from AIME and programming competitions represented in [LiveCodeBench](https://huggingface.co/datasets/livecodebench/code_generation_lite). The pinned LiveCodeBench dataset card labels its license only as `cc`; its loader declares MIT. Those declarations are recorded separately. The upstream Apache license is not a blanket license for all underlying competition material.

Full downloaded benchmark files and coding-test inputs remain in the ignored source cache. Selected statements, corrections, reference implementations, proofs, small fixtures, and derived expected outputs are tracked here. Raw model responses and encrypted reasoning are not included.
