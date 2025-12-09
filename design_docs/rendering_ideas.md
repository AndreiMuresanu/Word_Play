# Entity Stacking Visualization Options

Problem: When multiple entities occupy the same cell (e.g., Agent on Gold, or Multiple Agents), a single character cell cannot display all of them.

Goals:
1. Clarity for LLMs (text-based parsing).
2. Clarity for human debugging (visual).
3. Scalability (handling 2-4 stacked entities).

## Option 1: 2x2 Super-Grid (User Suggested)
Expand each logical "cell" into a 2x2 block of characters.
```
+--+--+
|A.|.G|  <-- Cell (0,0) has Agent (A) and Empty (.)
|..|..|      Cell (0,1) has Empty (.) and Gold (G)
+--+--+
```
**Pros:**
- Can show up to 4 entities per cell explicitly.
- Retains spatial grid structure.
**Cons:**
- Increases render size by 4x.
- Empty space can look cluttered if filled with dots.

## Option 2: Expanded Cell Width (1xN)
Expand width to accommodate multiple chars (e.g., `[AG]`).
```
| [A ] | [ G] |
| [  ] | [PA] |
```
**Pros:**
- Easier to read horizontally.
- Flexible width (can be 1x2 or 1x3).
**Cons:**
- Loses square aspect ratio aspect.

## Option 3: Unified List / Dictionary Representation
Render the grid with generic "multi" markers, but provide a coordinate list below.
```
| + | G |
| . | . |

Stacked Entities:
(0,0): [Agent_1, Agent_2]
```
**Pros:**
- Cleanest grid.
- Precise details available.
**Cons:**
- Requires cross-referencing eye movement.
- LLM has to parse two different sections.

## Option 4: Layered Rendering (Z-Index)
Render multiple "layers" of the map separately.
Layer 1 (Terrain):
```
| . | . |
```
Layer 2 (Items):
```
| . | G |
```
Layer 3 (Agents):
```
| A | . |
```
**Pros:**
- Very clear modification of standard grid.
**Cons:**
- Takes up 3x vertical space.
- Hard to mentally "merge" layers.

## Option 5: Hexadecimal/Count + Tooltip
Show the *count* of entities if > 1, or a special Hex code.
```
| 2 | G |
```
**Pros:**
- Compact.
**Cons:**
- Totally obscures identity of stacked agents (who is "2"?).

## Recommendation for "Word_Play" & LLM Usage
**Option 1 (2x2 Super-Grid)** or **Option 2 (Expanded Width)** are best because they keep all information "local" to the simplified spatial representation, which helps ResNets or CNN-like processing in Vision models or straightforward text parsing.

### Visual Improvements for Borders
Current issue: `+` used for borders AND stacked agents.
**Solution**:
1. Use Unicode Box Drawing characters for borders (`┌`, `─`, `│`).
2. Or use `#` for walls and ` ` (space) for void.
3. Reserve `+` only for specific semantic meaning or remove it entirely in favor of 2x2 view.
