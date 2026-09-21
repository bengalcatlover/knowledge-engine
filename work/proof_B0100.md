# Proof Certificate: B-0100

## 主張

有限非空集合 $D$ と $a^* \in D$ に対し、改善量関数を

$$C(f, a^*, D) = \max_{a \in D} \{ f(a) - f(a^*) \}$$

と定義する。このとき

$$C(f, a^*, D) = 0 \iff a^* \in \operatorname{argmax}_{a \in D} f(a)$$

## 証明

### (⇒) $C = 0 \implies a^* \in \operatorname{argmax}$

$C(f, a^*, D) = 0$ と仮定する。

定義より $\max_{a \in D} \{ f(a) - f(a^*) \} = 0$。

$D$ は有限非空なので最大値は達成される。
任意の $a \in D$ に対し $f(a) - f(a^*) \le 0$、
すなわち $f(a) \le f(a^*)$。

したがって $a^*$ は $f$ の $D$ 上の最大元であり、$a^* \in \operatorname{argmax}_{a \in D} f(a)$。 $\square$

### (⇐) $a^* \in \operatorname{argmax} \implies C = 0$

$a^* \in \operatorname{argmax}_{a \in D} f(a)$ と仮定する。

任意の $a \in D$ に対し $f(a) \le f(a^*)$、すなわち $f(a) - f(a^*) \le 0$。

$a^* \in D$ なので $f(a^*) - f(a^*) = 0$ であり、最大値は少なくとも0。

上界が0、下界が0なので $C(f, a^*, D) = 0$。 $\square$

## 依存する公理・定義

1. 有限非空集合上で実数値関数の最大値が存在する（有限集合の完備性）
2. $\operatorname{argmax}$ の定義：$\operatorname{argmax}_{a \in D} f(a) = \{a \in D \mid f(a) \ge f(a') \ \forall a' \in D\}$

## 証明の性質

- 構成的証明（非構成的選択公理を使わない）
- 有限集合に限定（無限集合への拡張は上限の存在を別途要する）
- 経験的前提を含まない（純粋に定義から導出）
