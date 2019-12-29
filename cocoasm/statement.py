"""
Copyright (C) 2019 Craig Thomas

This project uses an MIT style license - see LICENSE for details.
A Color Computer Assembler - see the README.md file for details.
"""
# I M P O R T S ###############################################################

import re

from copy import copy

from cocoasm.exceptions import ParseError, TranslationError
from cocoasm.instruction import INSTRUCTIONS
from cocoasm.operand import Operand
from cocoasm.helpers import hex_value

# C O N S T A N T S ###########################################################

# Pattern to recognize a blank line
BLANK_LINE_REGEX = re.compile(r"^\s*$")

# Pattern to parse a comment line
COMMENT_LINE_REGEX = re.compile(r"^\s*;\s*(?P<comment>.*)$")

# Pattern to parse a single line
ASM_LINE_REGEX = re.compile(
    r"^(?P<label>\w*)\s+(?P<mnemonic>\w*)\s+(?P<operands>[\w\[\]#$,+-\.\*]*)\s*[;]*(?P<comment>.*)$"
)

# Pattern to recognize a direct value
DIR_REGEX = re.compile(
    r"^<(?P<value>.*)"
)

# C L A S S E S  ##############################################################


class Statement(object):
    """
    The Statement class represents a single line of assembly language. Each
    statement is constructed from a single line that has the following format:

        LABEL   MNEMONIC   OPERANDS    COMMENT

    The statement can be parsed and translated to its Chip8 machine code
    equivalent.
    """
    def __init__(self, line):
        self.empty = True
        self.comment_only = False
        self.instruction = None
        self.label = None
        self.operand = Operand(None)
        self.comment = None
        self.size = 0
        self.address = None
        self.set_address(0x0)
        self.mnemonic = None
        self.op_code = None
        self.post_byte = None
        self.additional = None
        self.state = None
        self.parse_line(line)

    def __str__(self):
        op_code_string = ""
        if self.get_op_codes():
            op_code_string += self.get_op_codes()
        if self.get_post_byte():
            op_code_string += self.get_post_byte()
        if self.get_additional():
            op_code_string += " " + self.get_additional()

        return "${} {} {} {} {}  ; {} {}".format(
            self.get_address(),
            op_code_string.ljust(15, ' '),
            self.get_label().rjust(10, ' '),
            self.get_mnemonic().rjust(5, ' '),
            self.operand.get_string_value().rjust(15, ' '),
            self.get_comment().ljust(40, ' '),
            self.operand.operand_type
        )

    def get_address(self):
        """
        Returns the address for this statement.

        :return: the address for this statement
        """
        return self.address or "0000"

    def get_label(self):
        """
        Returns the label associated with this statement.

        :return: the label for this statement
        """
        return self.label or ""

    def get_mnemonic(self):
        """
        Returns the mnemonic for this statement.

        :return: the mnemonic for this statement
        """
        return self.mnemonic or ""

    def get_op_codes(self):
        """
        Returns the operation codes for this statement.

        :return: the operation codes for this statement
        """
        return hex_value(self.op_code) or None

    def get_additional(self):
        return hex_value(self.additional) or None

    def get_post_byte(self):
        return hex_value(self.post_byte) or None

    def get_comment(self):
        """
        Returns the comment for this statement.

        :return: the comment for this statement
        """
        return self.comment or ""

    def get_size(self):
        return self.size

    def is_empty(self):
        """
        Returns True if there is no operation that is contained within the
        statement.

        :return: True if the statement is empty, False otherwise
        """
        return self.empty

    def match_operation(self):
        """
        Returns the instruction with the specified mnemonic, or None if the
        mnemonic does not exist.

        :return: the instruction associated with the mnemonic
        """
        return next((op for op in INSTRUCTIONS if op.mnemonic == self.mnemonic), None)

    def is_comment_only(self):
        return self.comment_only

    def get_include_filename(self):
        """
        Returns the name of the file to include in the current stream of
        statements if the statement is the pseudo op INCLUDE, and there is
        a value for the operand

        :return: the name of the file to include
        """
        return self.operand.get_string_value() if self.instruction.is_include() else None

    def parse_line(self, line):
        """
        Parse a line of assembly language text.

        :param line: the line of text to parse
        """
        if BLANK_LINE_REGEX.search(line):
            return

        data = COMMENT_LINE_REGEX.match(line)
        if data:
            self.empty = False
            self.comment_only = True
            self.comment = data.group("comment").strip()
            return

        data = ASM_LINE_REGEX.match(line)
        if data:
            self.label = data.group("label") or None
            self.mnemonic = data.group("mnemonic") or None
            self.operand = Operand(data.group("operands"))
            self.comment = data.group("comment").strip() or None
            self.empty = False
            return

        raise ParseError("Could not parse line [{}]".format(line), self)

    def match_mnemonic(self):
        self.instruction = copy(self.match_operation())
        if not self.instruction:
            raise TranslationError("Invalid mnemonic [{}]".format(self.mnemonic), self)

    def set_address(self, address):
        self.address = hex_value(address, 4)

    def translate(self, symbol_table):
        """
        Translate the mnemonic into an actual operation.

        :param symbol_table: the dictionary of symbol table elements
        """
        if self.instruction.is_pseudo():
            self.additional = self.instruction.translate_pseudo(self.get_label(), self.operand, symbol_table)
            return

        if self.instruction.is_special():
            self.post_byte = self.instruction.translate_special(self.operand)
            return

        operand = self.operand
        if operand.is_symbol():
            symbol = operand.get_string_value()
            if symbol not in symbol_table:
                raise TranslationError("Unknown symbol [{}]".format(symbol), self)
            operand = Operand(symbol_table[symbol].get_address())
            if not operand.get_string_value():
                return

        if self.instruction.is_branch_operation():
            self.op_code = self.instruction.mode.rel
            # TODO: translate the relative address to branch to
            return

        if operand.is_inherent():
            if self.instruction.mode.supports_inherent():
                self.op_code = self.instruction.mode.inh
            else:
                raise TranslationError("Instruction [{}] requires an operand".format(self.mnemonic), self)

        if operand.is_immediate():
            if self.instruction.mode.supports_immediate():
                self.op_code = self.instruction.mode.imm
                self.additional = operand.get_immediate()
            else:
                raise TranslationError("Instruction [{}] does not support immediate addressing".format(self.mnemonic),
                                       self)

        if operand.is_extended_indirect():
            if self.instruction.mode.supports_indexed():
                self.op_code = self.instruction.mode.ind
                self.additional = operand.get_extended_indirect()
                # TODO: properly translate what the post-byte code should be
                self.post_byte = 0x9F
            else:
                raise TranslationError("Instruction [{}] does not support indexed addressing".format(self.mnemonic),
                                       self)

        if operand.is_direct():
            if self.instruction.mode.supports_direct():
                self.op_code = self.instruction.mode.dir
                self.additional = operand.get_string_value()
            else:
                raise TranslationError("Instruction [{}] does not support direct addressing".format(self.mnemonic),
                                       self)

        if operand.is_extended():
            if self.instruction.mode.supports_extended():
                self.op_code = self.instruction.mode.ext
                self.additional = operand.get_string_value()
            else:
                raise TranslationError("Instruction [{}] does not support extended addressing".format(self.mnemonic),
                                       self)

        if self.op_code:
            self.size += int((len(self.get_op_codes()) / 2))

        if self.additional:
            self.size += int((len(self.get_additional()) / 2))

        if self.post_byte:
            self.size += int((len(self.get_post_byte()) / 2))

# E N D   O F   F I L E #######################################################
