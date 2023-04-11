#!/usr/bin/env python
import sys
from collections import defaultdict

from messages_pb2 import (
    MessageType,
    wire_bootloader,
    wire_debug_in,
    wire_debug_out,
    wire_in,
    wire_no_fsm,
    wire_out,
)

fh = open("messages_map.h", "wt")
fl = open("messages_map_limits.h", "wt")

# len("MessageType_MessageType_") - len("_fields") == 17
TEMPLATE = "\t{{ {type} {dir} {cmd_flags} {msg_id:46} {fields:29} {process_func} }},\n"

LABELS = {
    wire_in: "in messages",
    wire_out: "out messages",
    wire_debug_in: "debug in messages",
    wire_debug_out: "debug out messages",
}

# interface-direction pairs
IFACE_DIR_PAIRS = {
    wire_in: ("n", "i"),
    wire_out: ("n", "o"),
    wire_debug_in: ("d", "i"),
    wire_debug_out: ("d", "o"),
}

SPECIAL_DEBUG_MESSAGES = {"MessageType_LoadDevice"}


def get_wire_extensions(message):
    extensions = message.GetOptions().Extensions
    return (ext for ext in IFACE_DIR_PAIRS if extensions[ext])


def handle_message(fh, fl, skipped, message, extension):
    name = message.name
    short_name = name.split("MessageType_", 1).pop()
    assert short_name != name

    interface, direction = IFACE_DIR_PAIRS[extension]

    for s in skipped:
        if short_name.startswith(s):
            return

    options = message.GetOptions()
    bootloader = options.Extensions[wire_bootloader]
    no_fsm = options.Extensions[wire_no_fsm]

    if getattr(options, "deprecated", None):
        fh.write(f"\t// Message {short_name} is deprecated\n")
        return
    if bootloader:
        fh.write(f"\t// Message {short_name} is used in bootloader mode only\n")
        return
    if no_fsm:
        fh.write(f"\t// Message {short_name} is not used in FSM\n")
        return

    if direction == "i":
        process_func = f"(void (*)(const void *))fsm_msg{short_name}"
    else:
        process_func = "0"

    cmd_flags = "CommandFlags_"
    if getattr(options, "factory", None):
        cmd_flags += "Factory_Only"
    else:
        cmd_flags += "Default"

    fh.write(
        TEMPLATE.format(
            type=f"'{interface}',",
            dir=f"'{direction}',",
            cmd_flags="%s," % cmd_flags,
            msg_id=f"MessageType_{name},",
            fields=f"{short_name}_fields,",
            process_func=process_func,
        )
    )

    encoded_size = None
    decoded_size = None
    t = interface + direction
    if t == "ni":
        encoded_size = "MSG_IN_ENCODED_SIZE"
        decoded_size = "MSG_IN_DECODED_SIZE"
    elif t == "no":
        encoded_size = "MSG_OUT_ENCODED_SIZE"
        decoded_size = "MSG_OUT_DECODED_SIZE"
    elif t == "do":
        encoded_size = "MSG_DEBUG_OUT_ENCODED_SIZE"
        decoded_size = "MSG_OUT_DECODED_SIZE"

    if encoded_size:
        fl.write(
            f'_Static_assert({encoded_size} >= {short_name}_size, "msg buffer too small");\n'
        )

    if decoded_size:
        fl.write(
            f'_Static_assert({decoded_size} >= sizeof({short_name}), "msg buffer too small");\n'
        )


skipped = sys.argv[1:]

fh.write(
    "\t// This file is automatically generated by messages_map.py -- DO NOT EDIT!\n"
)
fl.write(
    "// This file is automatically generated by messages_map.py -- DO NOT EDIT!\n\n"
)

messages = defaultdict(list)

for message in MessageType.DESCRIPTOR.values:
    if message.GetOptions().deprecated:
        continue
    for extension in get_wire_extensions(message):
        messages[extension].append(message)

for extension in (wire_in, wire_out, wire_debug_in, wire_debug_out):
    if extension == wire_debug_in:
        fh.write("\n#if DEBUG_LINK\n")
        fl.write("\n#if DEBUG_LINK\n")

    fh.write(f"\n\t// {LABELS[extension]}\n\n")

    for message in messages[extension]:
        if message.name in SPECIAL_DEBUG_MESSAGES:
            fh.write("#if DEBUG_LINK\n")
        handle_message(fh, fl, skipped, message, extension)
        if message.name in SPECIAL_DEBUG_MESSAGES:
            fh.write("#endif\n")

    if extension == wire_debug_out:
        fh.write("\n#endif\n")
        fl.write("#endif\n")

fh.close()
fl.close()
