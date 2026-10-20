"""PlatformIO extra script: adds the shared, plant and controller sources and the mode macros to an environment.

Environment variables (set by srmsil.hil.build, or by CI):
  SRM_HIL_GEN_DIR   folder with srm_motor_tables.h and hil_config.h
  SRM_CTRL_DIR      controller source folders, separated by os.pathsep (controller env only)
  SRM_HIL_MODES     current_sense,position[,dac], e.g. ad7606,encoder,mcp4922x2
  SRM_HIL_FIRMWARE_HASH  32-bit hash as hex digits
"""
import os
import sys

Import("env")  # noqa: F821  (provided by SCons)

HERE = env["PROJECT_DIR"]  # noqa: F821
REPO = os.path.dirname(HERE)
C_DIR = os.path.join(REPO, "src", "srmsil", "c")
name = env["PIOENV"]  # noqa: F821


def add_folder(folder, tag):
    env.Append(CPPPATH=[folder])  # noqa: F821
    env.BuildSources(os.path.join("$BUILD_DIR", "extra_" + tag), folder, "+<*.c>")  # noqa: F821


env.Append(CPPPATH=[C_DIR, os.path.join(HERE, name)])  # noqa: F821
add_folder(os.path.join(HERE, "common"), "hil_common")
if name == "emulator":
    add_folder(os.path.join(C_DIR, "plant"), "plant")
else:
    for i, d in enumerate(filter(None, os.environ.get("SRM_CTRL_DIR", "").split(os.pathsep))):
        add_folder(d, f"ctrl{i}")

gen = os.environ.get("SRM_HIL_GEN_DIR")
if gen:
    env.Append(CPPPATH=[gen])  # noqa: F821

sys.path.insert(0, os.path.join(HERE, "scripts"))
from hil_modes import mode_macros  # noqa: E402

try:
    flags = mode_macros(os.environ.get("SRM_HIL_MODES", ""))
except ValueError as e:
    sys.stderr.write("error: " + str(e) + "\n")
    env.Exit(1)  # noqa: F821
h = os.environ.get("SRM_HIL_FIRMWARE_HASH")
if h:
    flags.append(f"HIL_FIRMWARE_HASH=0x{h}")
env.Append(CPPDEFINES=flags)  # noqa: F821
