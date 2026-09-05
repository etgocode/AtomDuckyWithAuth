# keycodes_de.py
from adafruit_hid.keycode import Keycode

class KeyCodesDE:
    def __init__(self):
        self.keys = self.load_keys()
        
    def load_keys(self):
        keys_dict = {}
        
        # Letters (same physical position on DE and US)
        letters = 'abcdefghijklmnopqrstuvwxyz'
        for letter in letters:
            keycode_attr = getattr(Keycode, letter.upper(), None)
            if keycode_attr is not None:
                keys_dict[letter] = keycode_attr

        # z and y are swapped on DE layout
        keys_dict['z'] = Keycode.Y   # DE: z is on US-Y position
        keys_dict['y'] = Keycode.Z   # DE: y is on US-Z position

        # Numbers
        numbers = {
            "1": Keycode.ONE,
            "2": Keycode.TWO,
            "3": Keycode.THREE,
            "4": Keycode.FOUR,
            "5": Keycode.FIVE,
            "6": Keycode.SIX,
            "7": Keycode.SEVEN,
            "8": Keycode.EIGHT,
            "9": Keycode.NINE,
            "0": Keycode.ZERO
        }
        keys_dict.update(numbers)
        
        spacers = {
            " ": Keycode.SPACE,
            "	": Keycode.SPACE,
            "\n": Keycode.RETURN,
        }
        keys_dict.update(spacers)
        
        # DE keys mapped to physical US keycodes
        chars = {
            "ß": Keycode.MINUS,          # DE: ß / ? key (next to 0)
            "´": Keycode.EQUALS,         # DE: ´ / ` key (next to ß)
            "^": Keycode.GRAVE_ACCENT,   # DE: ^ / ° key (first key)
            "ü": Keycode.LEFT_BRACKET,
            "+": Keycode.RIGHT_BRACKET,
            "ö": Keycode.SEMICOLON,
            "ä": Keycode.QUOTE,
            "#": Keycode.BACKSLASH,
            "<": Keycode.KEYPAD_BACKSLASH,   # DE: < on the extra key left of Z
            ".": Keycode.PERIOD,             # DE: . on US period key
            ",": Keycode.COMMA,              # DE: , on US comma key
            "-": Keycode.FORWARD_SLASH,      # DE: - on / key
        }
        keys_dict.update(chars)
        
        # Special characters with Shift
        self.shift_char = {
            "!": Keycode.ONE,
            "\"": Keycode.TWO,
            "§": Keycode.THREE,
            "$": Keycode.FOUR,
            "%": Keycode.FIVE,
            "&": Keycode.SIX,
            "/": Keycode.SEVEN,
            "(": Keycode.EIGHT,
            ")": Keycode.NINE,
            "=": Keycode.ZERO,
            "?": Keycode.MINUS,           # Shift + ß / ? key
            "`": Keycode.EQUALS,          # Shift + ´ / ` key
            "°": Keycode.GRAVE_ACCENT,    # Shift + ^ / ° key
            "Ü": Keycode.LEFT_BRACKET,
            "Ö": Keycode.SEMICOLON,
            "Ä": Keycode.QUOTE,
            "'": Keycode.BACKSLASH,
            ":": Keycode.PERIOD,
            ";": Keycode.COMMA,
            "_": Keycode.MINUS,
            "*": Keycode.RIGHT_BRACKET,  # Shift + + / * key
            ">": Keycode.KEYPAD_BACKSLASH,   # DE: < on the extra key left of Z
            ";": Keycode.COMMA, 
            ":": Keycode.PERIOD,
            "_": Keycode.FORWARD_SLASH,
        }
        
        # AltGr combinations (RIGHT_ALT)
        self.altgr_char = {
            "{": Keycode.SEVEN,     # AltGr + 7
            "[": Keycode.EIGHT,     # AltGr + 8
            "]": Keycode.NINE,      # AltGr + 9
            "}": Keycode.ZERO,      # AltGr + 0
            "\\": Keycode.MINUS,    # AltGr + ß
            "@": Keycode.Q,         # AltGr + Q
            "€": Keycode.E,         # AltGr + E
            "~": Keycode.RIGHT_BRACKET, #AltGr + +
            "|": Keycode.KEYPAD_BACKSLASH, # AltGr + <
            "µ": Keycode.M,               # AltGr + M
        }
        
        # Uppercase letters
        uppercase_letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        for letter in uppercase_letters:
            keycode_attr = getattr(Keycode, letter, None)
            if keycode_attr is not None:
                self.shift_char[letter] = keycode_attr
        # Uppercase z and y swapped on DE layout
        self.shift_char['Z'] = Keycode.Y
        self.shift_char['Y'] = Keycode.Z
        
        self.system_chars = {
            "<ESC>": Keycode.ESCAPE,
            "<BSC>": Keycode.BACKSPACE,
            "<TAB>": Keycode.TAB,
            "<SCR>": Keycode.PRINT_SCREEN,
            "<SLK>": Keycode.SCROLL_LOCK,
            "<PAS>": Keycode.PAUSE,
            "<INS>": Keycode.INSERT,
            "<HOE>": Keycode.HOME,
            "<PGU>": Keycode.PAGE_UP,
            "<PGD>": Keycode.PAGE_DOWN,
            "<ARR>": Keycode.RIGHT_ARROW,
            "<ARL>": Keycode.LEFT_ARROW,
            "<ARD>": Keycode.DOWN_ARROW,
            "<ARU>": Keycode.UP_ARROW,
            "<NLK>": Keycode.KEYPAD_NUMLOCK,
            "<APP>": Keycode.APPLICATION,
            "<PWR>": Keycode.POWER, # macOS only
            "<GUI>": Keycode.GUI, # MAC or WINDOWS key / Search key for android/ ios
            "<CMD>": Keycode.GUI, 
            "<WIN>": Keycode.GUI,  
            "<CTL>": Keycode.LEFT_CONTROL,
            "<SPC>": Keycode.SPACEBAR,
            "<RET>": Keycode.RETURN
            }
        
        self.toggles = {
            "<CTRL>": Keycode.LEFT_CONTROL,
            "<LALT>": Keycode.LEFT_ALT,
            "<CTRR>": Keycode.RIGHT_CONTROL,
            "<RALT>": Keycode.RIGHT_ALT,
            "<GCMD>": Keycode.COMMAND, # or GUI or WINDOWS
            "<LSHT>": Keycode.LEFT_SHIFT,
            "<RSHT>": Keycode.RIGHT_SHIFT,
            "<CAPS>": Keycode.CAPS_LOCK
            }
        
        return keys_dict