# 🎲 Dice Roller Module

A simple, efficient utility for rolling RPG dice within OpenLumara.

## 🛠 Usage

### For Users
You can roll dice directly in the chat using the slash command:
`/roll <notation>`

**Examples:**
- `/roll 1d20` (Roll a single 20-sided die)
- `/roll 2d6 + 4` (Roll two 6-sided dice and add 4)
- `/roll 1d10 - 2` (Roll a 10-sided die and subtract 2)

### For AI Agents
The AI has access to the `roll_dice` tool. When a user asks to roll dice or a game situation requires a check, the AI should call this tool with the appropriate notation string.

**Tool Call Example:**
`roll_dice(notation="1d20 + 5")`

## ⚙️ Settings
- **crit_notifications (Boolean):** When enabled, the module will explicitly flag "Critical" rolls (natural 1s or maximum possible rolls for the die type).

## 📝 Technical Details
- **Notation Support:** `[number of dice]d[number of sides] [+/-] [modifier]`
- **Safety Cap:** Maximum of 1,000 dice per roll to prevent performance issues.
- **Language:** Python
