"""Child-side execution engine of pydblclick.

This module is launched by the parent supervisor (pydblclick/__main__.py) as:

    python -m pydblclick._child <script.py> [args...]

It runs the target script with plain-Python semantics (via runpy.run_path),
shows the traceback on uncaught exceptions, and displays the pause prompt/menu.
The interactive console (<i> menu option) has access to the script's real
globals since everything happens in this process.

If the pause prompt cannot be displayed (the script closed stdin with
exit()/quit(), or the interpreter dies), the parent supervisor takes over
and displays a fallback pause — so the console window never flashes away.

Child -> parent protocol: the environment variable PYDBLCLICK_STATUS_FILE
points to a file where the child writes "handled" once it has fulfilled its
pause-or-no-pause duty. If the marker is missing, the parent pauses itself.
"""
import os
import sys
import traceback
import code
import runpy

STATUS_HANDLED = "handled"

globalsParameter = {}  # global variable that will store the script's namespace


class StdinUnavailable(Exception):
    """Raised when the pause prompt cannot read stdin (closed by exit()/quit())."""


class User32:
    class Const:
        SW_HIDE = 0
        SW_SHOWNORMAL = 1
        SW_SHOWMINIMIZED = 2
        SW_SHOWMAXIMIZED = 3
        SW_SHOWNOACTIVATE = 4
        SW_SHOW = 5
        SW_MINIMIZE = 6
        SW_SHOWMINNOACTIVE = 7
        SW_SHOWNA = 8
        SW_RESTORE = 9
        SW_SHOWDEFAULT = 10
        SW_FORCEMINIMIZE = 11

    @staticmethod
    def show_window(n_cmd_show):
        """
        Sets the current window's show state.
        """
        # https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-showwindow
        import ctypes
        kernel32 = ctypes.WinDLL('kernel32')
        user32 = ctypes.WinDLL('user32')
        h_wnd = kernel32.GetConsoleWindow()
        user32.ShowWindow(h_wnd, n_cmd_show)


def have_console():
    """True if this process is attached to a console."""
    import ctypes
    return bool(ctypes.WinDLL('kernel32').GetConsoleWindow())


def ensure_console(title=None):
    """Attach a brand-new console to this process and rewire the standard streams.

    Used by windowless .pyw execution: the console only comes into existence
    when there is something to show (an exception). Returns False if a console
    could not be created.
    """
    import ctypes
    kernel32 = ctypes.WinDLL('kernel32')
    if not kernel32.GetConsoleWindow():
        if not kernel32.AllocConsole():
            return False
        sys.stdin = open("CONIN$", "r", encoding="utf-8", errors="replace")
        sys.stdout = open("CONOUT$", "w", buffering=1, encoding="utf-8", errors="replace")
        sys.stderr = open("CONOUT$", "w", buffering=1, encoding="utf-8", errors="replace")
    if title:
        kernel32.SetConsoleTitleW(str(title))
    return True


def reveal_console_for_pyw(log_file=None):
    """Make the console visible for a crashing .pyw script.

    Two situations:
    - a console exists (script launched from a console, or legacy hidden-console
      mode): just show its window again;
    - no console at all (windowless mode, parent is pythonw.exe): create one on
      the spot and replay the output captured so far in the log file.
    """
    if have_console():
        User32.show_window(User32.Const.SW_SHOWDEFAULT)
        return
    # Flush what the script wrote to the redirected stdout/stderr (the log
    # file) so the replay below is complete.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except (OSError, ValueError, AttributeError):
            pass
    if not ensure_console(title=os.path.basename(sys.argv[0]) + " -- pydblclick"):
        return
    if log_file:
        try:
            with open(log_file, encoding="utf-8", errors="replace") as f:
                captured = f.read()
            if captured:
                print(captured, end="")
        except OSError:
            pass


def showtraceback(script_path, script_excepthook=None):
    """
    Displays the exception that just occurred, hiding the pydblclick/runpy
    internal frames so the traceback starts at the user's script.

    script_excepthook: the excepthook installed by the script itself (None if
    the script did not change sys.excepthook).
    """
    sys.last_type, sys.last_value, last_tb = ei = sys.exc_info()
    sys.last_traceback = last_tb
    try:
        # Walk down to the first frame that belongs to the user's script.
        # Frames above it are pydblclick's own code and runpy internals.
        tb = last_tb
        while tb is not None and tb.tb_frame.f_code.co_filename != script_path:
            tb = tb.tb_next
        # tb is None for exceptions with no frame in the script (e.g. SyntaxError):
        # format_exception then prints the exception part only, which for a
        # SyntaxError still includes the file, line and caret indicator.
        lines = traceback.format_exception(ei[0], ei[1], tb)
        if script_excepthook is not None:
            # The *script* installed its own excepthook: let it take precedence
            # over our print. (Comparing against sys.__excepthook__ is not
            # enough: some environments replace sys.excepthook globally, which
            # would silently send our traceback elsewhere.)
            script_excepthook(ei[0], ei[1], tb)
        else:
            print(''.join(lines))
    finally:
        tb = last_tb = ei = None


def display_pause_prompt_and_menu():
    """
    Pauses a script to let the user read stdout and/or strerr before the window gets closed
    """
    # Looping on the pause message as long as it is needed
    while True:
        wait = None
        # Managing KeyboardInterrupt during the pausing message
        while wait is None:
            try:
                wait = input("Press <Enter> to Quit. (<c> for cmd console. <i> for interactive python. <r> to restart.)\n")
            except KeyboardInterrupt:
                pass  # The menu cannot be left using KeyboardInterrupt
            except EOFError:
                wait = ""  # stdin closed (e.g. piped input) -- treat as Enter
            except ValueError:
                # stdin has been closed by the script (exit()/quit() does that):
                # the parent supervisor must display the pause instead
                raise StdinUnavailable()
            except:
                print(traceback.format_exc())  # Unexpected exception

        # By default, the script is set to end after we break out of the "While True" loop displaying the pausing message
        must_run_script_again = False
        if wait.lower() == "c":
            print('Opening a windows console (cmd.exe). Type "exit" to quit.\n\n')
            try:
                os.system("cmd /k")
            except KeyboardInterrupt:
                pass
            except:
                print(traceback.format_exc())  # Unexpected exception
            print("\n")
        elif wait.lower() == "i":
            print('Opening python interactive console (python.exe). Type "Ctrl+Z to quit.\n\n')
            try:
                global globalsParameter
                # Import useful debug modules
                from pprint import pprint as pp
                globalsParameter['pp'] = pp
                globalsParameter['traceback'] = traceback
                globalsParameter['os'] = os
                globalsParameter['sys'] = sys
                code.interact(local=globalsParameter)
            except KeyboardInterrupt:
                pass
            except:
                print(traceback.format_exc())  # Unexpected exception
            print("\n")
        elif wait.lower() == "r":
            os.system("cls")
            must_run_script_again = True
            break
        elif wait.lower() == "debug":
            # Secret menu item to help developping new features
            print("place any variable here to debug it: " + sys.executable)
        elif wait.lower() == "pydblclick":
            # Secret feature to open the tool and start editing the source for new cool features
            os.system("explorer " + os.path.split(sys.argv[0])[0])
        elif wait.lower() == "":
            must_run_script_again = False
            break  # exits while True to end pydblclick
        else:
            # The commands must be typed accurately. Must retry...
            wait = None

    # Run after we brake out of the While True loop:
    return must_run_script_again


def _normalize_exit_code(system_exit):
    """Turn a SystemExit into a process exit code, like the interpreter does."""
    code_value = system_exit.code
    if code_value is None:
        return 0
    if isinstance(code_value, int):
        return code_value
    print(code_value)  # sys.exit("message") prints the message and exits 1
    return 1


def run_script(script_to_execute):
    """Runs the target script and returns (pause_decision, exit_code)."""
    ################ BEHAVIOUR CUSTOMIZATION ######
    pydblclick_customizations = {}
    pydblclick_customizations['must_pause_in_console'] = True  # This can be changed dynamicaly by the enhanced scripts
    pydblclick_must_change_title = True
    pydblclick_verbose = False
    # pydblclick_verbose = True  # Uncomment to debug with verbose mode

    if pydblclick_verbose: print("pydblclick activated.")

    script_extension = os.path.splitext(script_to_execute)[1]
    script_is_doubleclicked = (('PROMPT' not in os.environ)
                               or ('pydblclick_simulate_doubleclick' in os.environ)
                               or ('pyexewrap_simulate_doubleclick' in os.environ))  # legacy name
    # script_is_doubleclicked = True  # Uncomment this to simulate a double-clicked script even though you are using a console

    exit_code = 0
    # Snapshot to detect an excepthook installed by the script itself
    hook_before_script = sys.excepthook

    if "pythonw" in sys.executable:
        err_msg = "Error : pydblclick should never be running with pythonw.exe !\n" + str(sys.executable) + "\n" + str(sys.argv)
        print(err_msg)
        with open("error.txt", "w", encoding="UTF-8") as f:
            f.write(err_msg)

    try:
        ################ INITIALIZATION ##############
        if pydblclick_verbose:
            print("interpreter is " + sys.executable)
            print("CLI is " + " ".join(sys.argv))
            print("script extension is " + script_extension)
            print("script_is_doubleclicked=" + str(script_is_doubleclicked))

        # .pyw files should have no visible console unless an exception occurs.
        # In windowless mode (parent is pythonw.exe) there is no console at all;
        # otherwise (legacy/CLI) the existing console window is hidden.
        if script_extension == ".pyw" and script_is_doubleclicked and have_console():
            User32.show_window(User32.Const.SW_HIDE)  # Use SW_SHOWMINIMIZED to debug

        # if not run in console (but through double-click) the window title will be explicit
        if script_is_doubleclicked and pydblclick_must_change_title and have_console():
            os.system("title " + os.path.basename(script_to_execute) + " -- pydblclick " + script_to_execute)

        ################ EXECUTION ####################
        # runpy.run_path() executes the script with plain-Python semantics:
        # a fresh __main__ module, __file__ set to the script path, real module
        # globals. No namespace reconstruction, no exec() surgery.
        # Like `python script.py`, the script's directory must be on sys.path:
        script_dir = os.path.dirname(os.path.abspath(script_to_execute))
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)

        # The customization dict is exposed through builtins so that scripts can
        # write `pydblclick_customizations['must_pause_in_console'] = False`
        # without pydblclick polluting their namespace.
        import builtins
        builtins.pydblclick_customizations = pydblclick_customizations
        builtins.pyexewrap_customizations = pydblclick_customizations  # legacy alias
        try:
            global globalsParameter
            globalsParameter = runpy.run_path(script_to_execute, run_name="__main__")
        finally:
            del builtins.pydblclick_customizations
            del builtins.pyexewrap_customizations

        if pydblclick_verbose: print("must_pause_in_console=" + str(pydblclick_customizations['must_pause_in_console']))

    except SystemExit as e:
        # exit()/quit()/sys.exit() in the script: not an error, but the exit
        # code must be propagated for CLI/batch callers.
        exit_code = _normalize_exit_code(e)
    except BaseException:
        exit_code = 1
        pydblclick_customizations['must_pause_in_console'] = True
        if script_extension == ".pyw":
            # From now on pydblclick will consider the script as a .py file (with a pausing message to display)
            script_extension = ".py"
            reveal_console_for_pyw(os.environ.get("PYDBLCLICK_PYW_LOG"))
        # Expose the script's globals to the interactive console for post-mortem debugging
        tb = sys.exc_info()[2]
        while tb is not None:
            if tb.tb_frame.f_code.co_filename == script_to_execute:
                globalsParameter = tb.tb_frame.f_globals
                break
            tb = tb.tb_next
        script_excepthook = sys.excepthook if sys.excepthook is not hook_before_script else None
        showtraceback(script_to_execute, script_excepthook)
        print("This exception has ended the script before the end.")

    pause_decision = script_is_doubleclicked and pydblclick_customizations['must_pause_in_console'] and script_extension != ".pyw"
    if pydblclick_verbose:
        print("pausing message ?")
        print("script_is_doubleclicked=" + str(script_is_doubleclicked))
        print("must_pause_in_console=" + str(pydblclick_customizations['must_pause_in_console']))
        print("script_extension=" + script_extension)
        print("pause_decision=" + str(pause_decision))

    return pause_decision, exit_code


def _write_status(status_file, text):
    if not status_file:
        return
    try:
        with open(status_file, "w", encoding="UTF-8") as f:
            f.write(text)
    except OSError:
        pass


def main():
    # sys.version_info(major=3, minor=11, micro=3, releaselevel='final', serial=0)
    if sys.version_info.major < 3 or sys.version_info.minor < 10:
        print("Warning: pydblclick has not been tested with Python version 3.9 and below.")
        print("sys.version=" + sys.version)

    if len(sys.argv) < 2:
        print("Usage: python -m pydblclick <script.py> [args...]")
        return 2

    status_file = os.environ.pop("PYDBLCLICK_STATUS_FILE", None)

    script_to_execute = sys.argv[1]
    # The wrapped script must see the same sys.argv as if it was run directly
    sys.argv = sys.argv[1:]

    exit_code = 0
    # Looping since the script can be run multiple times
    must_run_script_again = True
    while must_run_script_again:

        # But in most cases the script is only run once
        must_run_script_again = False

        # The script is run, depending on the situation there should be a pausing prompt
        pause_decision, exit_code = run_script(script_to_execute)

        # Displaying the pausing prompt (and defining if the script must be run again)
        if pause_decision:
            try:
                must_run_script_again = display_pause_prompt_and_menu()
            except StdinUnavailable:
                # The script closed stdin (exit()/quit() does that). No status
                # marker is written: the parent supervisor will pause instead.
                return exit_code

    _write_status(status_file, STATUS_HANDLED)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
