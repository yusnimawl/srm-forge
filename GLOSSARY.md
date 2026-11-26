# srm-forge

The words the owner and the sessions use for the project's goals and plan. The engine's technical terms are on the Notion wiki's Glossary page.

## Goal

**Bike motor**:
The first motor the tool designs: a traction motor for the owner's motorcycle (250 to 300cc class), driving the wheel through a planetary gear, with the motor at up to 20 000 rpm.
_Avoid_: bench target, bench motor

**Bike target**:
The numbers the bike motor must meet: peak and continuous power, top speed, rear wheel size and the gear ratios to try.
_Avoid_: bike spec, requirements (alone)

**Design voltage**:
The lowest battery voltage at which the bike motor must still give full peak power: 300 V. Below it the bike may give less power.
_Avoid_: minimum bus voltage (the empty battery goes lower), nominal voltage

**Total ratio**:
Motor speed divided by rear wheel speed, through the planetary gear and the chain or belt together.
_Avoid_: gear ratio (alone), reduction

**Power density**:
Rated power per active mass (kW/kg), or per active volume (kW/L), counted on the motor alone (stator, rotor, winding). Higher is better. The goal is the highest power density.
_Avoid_: specific power

**Order pack**:
The set of files and sheets jystator needs to make the stator and rotor stacks and the wound stator of one design.
_Avoid_: fabrication package (that name means the full roadmap step, which includes the datasheet)

## Plan

**Owner summary**:
The five-line, plain-language status at the top of the wiki front page: what works, what is being worked on, what waits on the owner, the next milestone and what is parked.
_Avoid_: snapshot, current priorities

**Keep**:
On the path to ordering the bike motor.

**Later**:
Useful, but not on the path to the bike motor. Parked until the bike motor is ordered.
_Avoid_: deferred, low priority

**Dropped**:
Not to be done. Kept on the Tracker as Parked with the reason.

**Accuracy target**:
The owner's 10 to 15 % agreement between the tool and measurement. Owner-facing text states gaps against it.
_Avoid_: budget (the uncertainty budget is the engine's own worst-case estimate, a different thing)
