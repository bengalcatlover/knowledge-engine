# Proof Certificate: B-0200 — Shannon Source Coding Theorem

## Statement

For a discrete memoryless source X with entropy H(X), no lossless coding scheme
can achieve an average code length L < H(X). Furthermore, there exists a prefix-free
code (e.g., Huffman code) achieving H(X) ≤ L < H(X) + 1.

## Proof Sketch (Lower Bound)

By Kraft's inequality, any uniquely decodable code with codeword lengths l₁, ..., lₙ
satisfies Σ 2^(-lᵢ) ≤ 1.

The average code length L = Σ pᵢ lᵢ.

Using the non-negativity of KL divergence D(p || q) ≥ 0 where qᵢ = 2^(-lᵢ) / Σ 2^(-lⱼ):

L - H(X) = Σ pᵢ lᵢ + Σ pᵢ log₂ pᵢ
          = Σ pᵢ log₂(pᵢ / 2^(-lᵢ))
          ≥ Σ pᵢ log₂(pᵢ / qᵢ) - log₂(Σ 2^(-lᵢ))
          ≥ 0 - 0 = 0

Therefore L ≥ H(X). □

## Proof Sketch (Achievability)

Choosing lᵢ = ⌈-log₂ pᵢ⌉ satisfies Kraft's inequality (since Σ 2^(-⌈-log₂ pᵢ⌉) ≤ Σ pᵢ = 1)
and gives:

-log₂ pᵢ ≤ lᵢ < -log₂ pᵢ + 1

Therefore: H(X) ≤ L < H(X) + 1. □

## Scope

- Applies to: discrete, finite-alphabet, memoryless (i.i.d.) sources
- Does not apply to: continuous sources (requires differential entropy), sources with memory (requires block coding), lossy compression (requires rate-distortion theory)
- No empirical premises: purely mathematical (combinatorics + information inequality)

## Source

Shannon, C. E. (1948). "A Mathematical Theory of Communication." Bell System Technical Journal, 27(3), 379–423. doi:10.1002/j.1538-7305.1948.tb01338.x
Theorem 9 (Noiseless Coding Theorem), Section 9.
