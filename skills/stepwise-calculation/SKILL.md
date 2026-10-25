---
name: stepwise-calculation
description: Use when a calculation needs more than one step, like a word problem, a price with discount and tax, percentages of percentages, or a unit conversion.
---

# Stepwise calculation

Break the problem into small steps, calculate every step with the calculate tool, and show the user each step, so they can follow and check it.

## Steps

1. **Write down what is given and what is asked.** The numbers with their units, and what the final answer should be.
2. **Plan the steps.** One calculation per step, in order. Say for each step what it calculates, e.g. "the price after the discount".
3. **Calculate every step with calculate.** Never in your head, not even easy ones.
   - Steps that don't need each other's results: ask for them in the same reply. They run at the same time.
   - A step that needs an earlier result: wait for that result, then use it.
4. **Use the exact results.** Copy the number calculate gave you into the next step. Don't round between steps: round only the final answer.
5. **Check the final answer.** Is it plausible (a discount makes a price smaller, a part is smaller than the whole)? Are the units right?

## What calculate accepts

- Only digits, spaces and `+ - * / ( ) . %`. No units, no words, no letters.
- No thousands separators: `2,340` is written `2340`.
- A percentage is a factor: 17% of 2340 is `0.17 * 2340`. A 20% discount is `* 0.8`, 19% tax added is `* 1.19`.
- A power is `**`: 2 to the power of 10 is `2 ** 10`.
- `%` alone is the remainder of a division, not percent: `7 % 3` is 1.
- Use parentheses when the order matters: `(120 + 30) * 1.19`, not `120 + 30 * 1.19`.

## How to answer

Show the steps as a numbered list, each with what it calculates, the expression, and the result. Then the final answer on its own line, rounded sensibly and with its unit:

1. Price after 20% discount: `120 * 0.8` = 96
2. Plus 19% tax: `96 * 1.19` = 114.24

**Final price: 114.24 €**
