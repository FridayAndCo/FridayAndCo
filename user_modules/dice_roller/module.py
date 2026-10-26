import core
import random
import re

class DiceRoller(core.module.Module):
    """
    A utility module for rolling RPG dice using standard notation.
    Supports formats like '2d6', '1d4 +1', etc...
    """
    category = "Utility"

    # -------------------------
    #   CONFIGURATION
    # -------------------------
    settings = {
        "crit_notifications": {
            "type": "boolean",
            "description": "Notify when a natural 1 or a maximum roll is achieved.",
            "default": True
        }
    }

    # -------------------------
    #   AI TOOLS
    # -------------------------

    @core.module.tool
    async def roll_dice(self, notation: str):
        """
        Rolls dice based on standard RPG notation.

        Args:
            notation: The dice notation to roll (e.g., '2d6', '1d20+5', '1d4-1').
        """
        result = await self._perform_roll(notation)
        if isinstance(result, str) and "Invalid" in result:
            return self.result(result, success=False)
        
        return self.result(result, success=True)

    # -------------------------
    #   USER-FACING COMMANDS
    # -------------------------

    @core.module.command("roll", help={
        "": "Rolls dice using RPG notation (e.g., /roll 2d6 + 2)",
        "notation": "The dice notation to roll"
    })
    async def roll_command(self, args: list):
        if not args:
            return "Please provide dice notation. Example: `/roll 1d20 + 5`"
        
        notation = " ".join(args)
        return await self._perform_roll(notation)

    # -------------------------
    #   HELPERS
    # -------------------------

    async def _perform_roll(self, notation: str) -> str:
        # Regex to match XdY and optional modifier +/- Z
        # Supports: 1d20, 2d6+4, 1d10 - 2, etc.
        pattern = r"(\d+)\s*d\s*(\d+)(?:\s*([+-])\s*(\d+))?"
        match = re.search(pattern, notation.lower())

        if not match:
            return "Invalid dice notation. Please use a format like '2d6' or '1d20 + 5'."

        try:
            num_dice = int(match.group(1))
            sides = int(match.group(2))
            modifier_sign = match.group(3)
            modifier_val = int(match.group(4)) if match.group(4) else 0
        except ValueError:
            return "Error parsing dice numbers. Please ensure you use integers."

        # Safety cap to prevent resource exhaustion
        if num_dice > 1000:
            return "Too many dice! Please roll 1000 or fewer."

        rolls = [random.randint(1, sides) for _ in range(num_dice)]
        base_total = sum(rolls)
        
        # Calculate final total with modifier
        final_total = base_total
        if modifier_sign == '+':
            final_total += modifier_val
        elif modifier_sign == '-':
            final_total -= modifier_val

        # Handle Criticals if enabled in settings
        crit_msg = ""
        if self.config.get("crit_notifications"):
            crits = [r for r in rolls if r == 1 or r == sides]
            if crits:
                crit_details = [f"{r}s" for r in crits]
                crit_msg = f" [Crits: {', '.join(crit_details)}]"

        # Build output string
        result_str = f"🎲 Rolled {num_dice}d{sides}: {rolls} = {base_total}"
        if modifier_sign:
            result_str += f" {modifier_sign} {modifier_val} = {final_total}"
        else:
            result_str += f" (Total: {final_total})"
        
        result_str += crit_msg

        return result_str
