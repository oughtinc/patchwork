"""Basic Functional HCH"""

import sys

from .datastore import Datastore
from .scheduling import Scheduler
from .interface import UserInterface


def main(argv):
    db = Datastore()
    sched = Scheduler(db)

    print("What is your root question?")

    sched.ask_root_question(input("> "))
    initial_context = sched.choose_context()
    ui = UserInterface(db, sched, initial_context)
    ui.cmdloop()

if __name__ == "__main__":
    main(sys.argv)

