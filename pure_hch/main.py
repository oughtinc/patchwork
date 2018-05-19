"""Basic Functional HCH"""

import sys

from .datastore import Datastore
from .scheduling import Scheduler
from .interface import UserInterface


def main(argv):
    db = Datastore()
    print("What is your root question?")
    sched = Scheduler(input("> "), db)
    ui = UserInterface(db, sched)
    ui.cmdloop()

if __name__ == "__main__":
    main(sys.argv)

