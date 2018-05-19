import cmd

from typing import Optional

import parsy

from .datastore import Datastore
from .scheduling import Action, Scheduler, Context, AskSubquestion, Reply, Unlock, Scratch

class UserInterface(cmd.Cmd):
    prompt = "> "

    def __init__(self, db: Datastore, scheduler: Scheduler, initial_context: Context) -> None:
        super().__init__()
        self.db = db
        self.scheduler = scheduler
        self.current_context = initial_context
        self.prompt = "{}\n{}".format(str(self.current_context), UserInterface.prompt)

    def precmd(self, line: str) -> str:
        print("---")
        return line

    def emptyline(self) -> bool:
        return False

    def postcmd(self, stop: bool, line: str) -> bool:
        self.prompt = "{}\n{}".format(str(self.current_context), UserInterface.prompt)
        return stop

    def _do(self, prefix: str, action: Action) -> None:
        try:
            self.scheduler.resolve_action(self.current_context, action)
            self.current_context = self.scheduler.choose_context()
        except parsy.ParseError as p:
            print("Your command was not parsed properly. Review the README for syntax.")
            print(p)
        except ValueError as v:
            print("Encountered an error with your command: ")
            print(v)
        return False


    def do_ask(self, arg: str) -> bool:
        return self._do("ask", AskSubquestion(arg))

    def do_reply(self, arg: str) -> bool:
        return self._do("reply", Reply(arg))

    def do_unlock(self, arg: str) -> bool:
        return self._do("unlock", Unlock(arg))

    def do_scratch(self, arg: str) -> bool:
        return self._do("scratch", Scratch(arg))


