import cmd
from traceback import print_exc

from typing import Optional

import parsy

from .actions import Action, AskSubquestion, Reply, Unlock, Scratch
from .context import Context
from .datastore import Datastore
from .scheduling import Session

class UserInterface(cmd.Cmd):
    prompt = "> "

    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session
        self.current_context = session.current_context
        self.initial_context = self.current_context
        self.update_prompt()

    def update_prompt(self) -> None:
        self.prompt = "{}\n{}".format(str(self.current_context), UserInterface.prompt)

    def precmd(self, line: str) -> str:
        print("-" * 80)
        return line

    def emptyline(self) -> bool:
        return False

    def postcmd(self, stop: bool, line: str) -> bool:
        self.update_prompt()
        return stop

    def _do(self, prefix: str, action: Action) -> bool:
        try:
            result = self.session.act(action)
            if isinstance(result, Context):
                self.current_context = result
            else:
                print("The initial context was:\n {}".format(self.initial_context))
                print("The final answer is:\n {}".format(result))
                return True
        except parsy.ParseError as p:
            print("Your command was not parsed properly. Review the README for syntax.")
            print(p)
        except ValueError as v:
            print("Encountered an error with your command: ")
            print_exc()
        except KeyError as k:
            print("Encountered an error with your command: ")
            print_exc()
        return False

    def do_ask(self, arg: str) -> bool:
        "Ask a subquestion of the current question."
        return self._do("ask", AskSubquestion(arg))

    def do_reply(self, arg: str) -> bool:
        "Provide a response to the current question."
        return self._do("reply", Reply(arg))

    def do_unlock(self, arg: str) -> bool:
        "Unlock a pointer in the current workspace."
        return self._do("unlock", Unlock(arg))

    def do_scratch(self, arg: str) -> bool:
        "Rewrite the Scratchpad."
        return self._do("scratch", Scratch(arg))

    def do_exit(self, arg: str) -> bool:
        "Leave the program, saving if a file was specified."
        return True


