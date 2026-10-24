# Independent mathematical review

Reviewer: root implementation agent, separate from the derivation author (`provider`).
The trigonometric certificate was authored by root and independently audited and
rerun by `provider`; see `TRIG_INDEPENDENT_REVIEW.md`. This is a review of explicit
proofs and executable exact certificates, not agreement between model answers.
All computational reference code ran only inside the pinned Docker sandbox.
No experimental model outcomes were consulted and no paid calls were made.

I checked the actual released source pairs, the derivations, and domain/existence
conditions. The following are the substantive review conclusions, in the existing
review order. No statement or correction was repaired.

| Rank / source ID | Independent finding |
| --- | --- |
| 1 / 1004 | Order8 forces p≡1 mod8; p=2 fails. Full Hensel lifting independently reproduces the two complete root sets, proving minima399 and110. The even-witness condition does not change existence modulo an odd modulus. |
| 2 / 1027 | Mod9 digit replacement forces all five digits4. Independent four-digit vector enumeration gives exactly5624 and5694 in the corrected problem. |
| 3 / 1003 | Separate rigorous interval review and a different-precision/asymmetric-partition certificate validate1244 and385. See the dedicated review. |
| 4 / 1025 | Exclusion confirmed: equiangular convex hexagon side directions force the three extended alternating-side lines to form an equilateral triangle; unequal listed side lengths contradict it. |
| 5 / 1024 | The log system has invertible coefficient matrix (eigenvalues−1,2,2); every resulting real log corresponds to a positive variable. Exact substitution and target fractions give221 and33. |
| 6 / 1058 | Exclusion confirmed independently from AC>BC=40 and AC≤AL+LC=36. |
| 7 / 1013 | Exclusion confirmed from two explicit different-size triangles with all circles inside. The source does not impose tangency to the common third side; adding it would change the problem. |
| 8 / 1030 | Polynomial division has remainder1 for every permitted initial base, hence the standard empty product is1. The source does not assert nonemptiness. Corrected bases21,49 follow from divisors of56, giving70. |
| 9 / 1006 | Exclusion confirmed: compact positive feasible set gives a maximum; Lagrange subtraction forces a repeated side. The irreducible cubic and degree argument imply irrational squared enclosing radius, contradicting the asserted rational form. The exact polynomial reduction is checked separately. |
| 10 / 1059 | Exclusion confirmed by leading-term growth: quartic divided by x tends to positive infinity as x→positive infinity. An initial global maximum cannot exist on the stated domain. |
| 11 / 1044 | Independent complete enumeration over ordered *integer* pairs, with a third-coordinate cube histogram, reproduces10174168 and885735. This differs from the author's paired-residue-frequency loop and preserves zero/endpoints/order. |
| 12 / 1028 | Exclusion confirmed: torus outer radius12 exceeds sphere radius11; axial internal tangency equation has no real solution. Repeated external-tangency wording in corrected statement is also inconsistent with its positive difference. |
| 13 / 1049 | Exclusion confirmed: the explicitly included diagram gives J on AF, while revised prose gives J on CF; distinct arc vertices prohibit identifying J with their intersection F. This is a conflicting specification, not a difficulty exclusion. |
| 14 / 1042 | Checked conditional quadrant-pair probabilities and cyclic endpoint alternation; crossing probabilities3/8 and17/36 include equal-pair, shared-quadrant and disjoint-pair events. Linearity of expectation with fixed diameters gives1923/8 and204. |
| 15 / 1012 | Independently expand z=4exp(iθ); real coefficients are363,−331 and324,−432. Cauchy–Schwarz is attained, giving sqrt(241330) and540 exactly. Irrationality is not an exclusion. |
| 16 / 1016 | Euler's identity plus the right triangle give sin²(A/2)=r/(2R). Area/half-angle identities imply adjacent-side product6Rr. For each listed r/R, cos((B−C)/2)=2sin(A/2) lies in the admissible interval; B,C are positive. Thus the necessary product is attained. |
| 17 / 1053 | Count each nonextreme level twice per complete period, zero with omitted boundary correction, and extrema once per period. Only extrema have quadratic contact, so initial n−t203 and updated n+t149 are justified. |
| 18 / 1019 | An independent exact rational determinant of cI−2P+P² for the cyclic permutation P gives177542 and8321. This independently checks the author's quadratic-root recurrence and reduction to42/321. |
| 19 / 1037 | Exclusion confirmed: initial tangent-line condition yields k=−27±10sqrt(10), product−271, contradicting positive m,n. |
| 20 / 1057 | Initial numerator is odd and coprime to mn, so no cancellation invalidates modular recurrence. Corrected gcd is exactly3 and the next sum is s²/3. Independent modular iteration using inverse3 mod1000 gives248. Initial2025 transitions give809. |
| 21 / 1031 | Affine normalization preserves ratios of areas; explicit reflected coordinates and shoelace formula give49/24. The stated areas/side lengths permit sinA<1, so these are realizable geometries. |
| 22 / 1008 | Misère odd-removal parity and the normal-play mod5 inductive strategy agree with the given player order and finite bounds. Supplemental reviewed reference only; no substitution in the first12. |

The independent check in `independent_exact_check.py` completed with exit0;
`independent-exact-run.json` records its source checksum and exact outputs.
The author's complete finite enumeration and exclusion certificates remain recorded
separately. Approval is based on the proof arguments and exhaustive/certified
calculations; small examples alone would not validate a reference.
