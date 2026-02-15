from __future__ import annotations

from typing import TYPE_CHECKING

from BaseClasses import Entrance, Region

if TYPE_CHECKING:
    from .world import APQuestWorld

# A region is a container for locations ("checks"), which connects to other regions via "Entrance" objects.
# Many games will model their Regions after physical in-game places, but you can also have more abstract regions.
# For a location to be in logic, its containing region must be reachable.
# The Entrances connecting regions can have rules - more on that in rules.py.
# This makes regions especially useful for traversal logic ("Can the player reach this part of the map?")

# Every location must be inside a region, and you must have at least one region.
# This is why we create regions first, and then later we create the locations (in locations.py).


def create_and_connect_regions(world: APQuestWorld) -> None:
    create_all_regions(world)
    connect_regions(world)


def create_all_regions(world: APQuestWorld) -> None:
    main = Region("Main", world.player, world.multiworld)
    blue = Region("Blue", world.player, world.multiworld)
    purple = Region("Purple", world.player, world.multiworld)
    blurple = Region("Blurple", world.player, world.multiworld)
    yellow = Region("Yellow", world.player, world.multiworld)

    # Let's put all these regions in a list.
    regions = [main, blue, purple, blurple, yellow]

    # # In our case, the Hammer locks the top middle chest in its own room if the hammer option is enabled.
    # if world.options.hammer:
    #     top_middle_room = Region("Top Middle Room", world.player, world.multiworld)
    #     regions.append(top_middle_room)

    # We now need to add these regions to multiworld.regions so that AP knows about their existence.
    world.multiworld.regions += regions


def connect_regions(world: APQuestWorld) -> None:
    # We have regions now, but still need to connect them to each other.
    # But wait, we no longer have access to the region variables we created in create_all_regions()!
    # Luckily, once you've submitted your regions to multiworld.regions,
    # you can get them at any time using world.get_region(...).
    main = world.get_region("Main")
    blue = world.get_region("Blue")
    purple = world.get_region("Purple")
    blurple = world.get_region("Blurple")
    yellow = world.get_region("Yellow")

    main.connect(blue, "Main to Blue", lambda state: state.has("Blue", world.player))
    main.connect(purple, "Main to Purple", lambda state: state.has("Purple", world.player))
    main.connect(blurple, "Main to Blurple", lambda state: state.has_all(["Blue", "Purple"], world.player))
    main.connect(yellow, "Main to Yellow", lambda state: state.has("Yellow", world.player))

    # # Some Entrances may only exist if the player enables certain options.
    # # In our case, the Hammer locks the top middle chest in its own room if the hammer option is enabled.
    # # In this case, we previously created an extra "Top Middle Room" region that we now need to connect to Overworld.
    # if world.options.hammer:
    #     top_middle_room = world.get_region("Top Middle Room")
    #     overworld.connect(top_middle_room, "Overworld to Top Middle Room")
