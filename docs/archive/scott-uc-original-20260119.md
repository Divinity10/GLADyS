use cases

###General Guidance
1.  Things the brain has learned about the user (risk tolerance, aggressiveness, typical conditions given, etc) affect how and when (or if) the brain takes action
2.  The brain's personality affects its actions. An aggressive personality acts more aggressively than a passive one
3.  Tone of brain's communication is affected by its personality and constraints from user
4.  User contraints affect behavior and communication. E.g. User says "no profanity", then the brain doesn't use profanity. User says "swear often" then the fucking brain swears all the fucking time and gives user shit.
5.  User's general preferences should be assessed within context. E.g.
    a) User's tolerance of discomfort when temp is slightly outside of comfort zone. 
    b) Effect on utility cost given the environmental conditions
        - door open, don't turn on AC
        - extreme temp difference between indoor & outdoor + user sensitivity to utility costs
6.  Explicit instructions >> learned behavior
    a) User says to never alert them after 10pm, brain learns that the user likes alert when wash is done. Wash finishes at 10:30pm -> do NOT alert the user
7.  Vague instructions that imply a contradiction of what's learned of user or global rules the user has set, should trigger clarifying questions/statements.
    a) User says to never alert them after 10pm. User is playing a game at 11pm. Brain should ask if they want alerts until they are done playing the game.
    b) User says to set temp to 78F, which is outside of their normal comfort zone. Brain should ask if that's what they really want (phrasing matters: could ask "Are you sure about 78F" or "Did you actually mean 78F?") and ask for how long they want that temp OR if the change is permenant or just for now.
    c) User has global instruction to never help when they do PVP. User appears to be planning an attack on a player they are unlikely to beat. Brain should ask "Are you sure you want to attack that player? You are unlikely to win" or "Your win probability is only X%. Are you sure attacking them is a good idea?"
    d) User says to never interrupt them from 10am until Noon. User gives a command to alert them when a package is delivered. Brain should ask "Alert even if it arrives between 10am or Noon?" or "Will do, but I may need to alert you between 10am and Noon."
8.  Goal is to store user's data local rather than remote, but user may need to use remote LLMs/sensors/actuators
    a) Must consider message size & content
    b) What configuration settings should we have for users to set their tolerance for data sharing
        - Performance may require storing user data on a remote db near a remote LLM. user config to allow that
        - Need to know what use cases may be affected by this guidance
9.  Need to understand performance issues/constraints/requirements a use case has to be actually usable 
10. NEVER violate core principles
    a) Do not injure real people
    b) Do not obviously help break the law
    c) For certain extra sensitive areas, don't even engage in hypotheticals.
        - Child pornography
        - Rape
        - etc


## A. Games - Passive
1.  User asks brain to mine X resource
    a) brain either controls character to perform gathering OR provides locations of resources
    b) brain asks user for how long/how much and/or within what radius of current position

2.  User asks brain to watch for threats while I do <whatever>
    a)  brain watches for hostile monsters/players and alerts user
    b)  if actions are allowed:
        - brain asks user what they should do if a hostile is detect or maybe a more specific question like "should I switch gear if a hostile is detected?"
    - if yes, then brain performs the action defined when a hostile is detected

3.  User asks brain to provide guidance on how to defeat a hostile (monster/npc/player)
    a)  brain identifies the hostile. if unsure, it asks the user which hostile the user wants to defeat
    b)  brain determines expected capabilities of target and the user, devises a plan, and makes suggestion to user

4.  User asks brain to watch for X OR alert me when X happens OR if you see X...and do Y
    a)  brain monitors for the appearance of X (X is essentially a trigger)
    b)  brain performs Y when trigger happens

5.  User says in X time, do Y
    a) brain does Y after X time expires

## B. Games - Proactive
1.  brain notices the user appears to be hunting for bosses/monsters
    a) brain asks user if they want help finding bosses/monsters. possibly asks for criteria of search (type, level, etc)
    b) brain notifies the user of bosses/monsters they see

2.  brain notices a hostile approaching user
    a) brain alerts user
    b) brain swaps gear (if actions supported)
    c) brain takes actions to defend user's character (if actions supported)
    d) aggressiveness of action depends on user personality/instructions and maybe the AI personality

3.  brain notices a rare monster/resource
    a)  alerts user (voice or text)
    b)  if actions are allowed and user has previously approved, attempt to collect/kill monster/resource
        - attacking should be a higher threshold because risks are greater. what if player dies? what if it's a trap? how much risk is the user OK with?

4.  brain notices the user dropped something OR left loot behind
    a)  alerts user


## C. Home Environment - Passive
1.  User asks to set the heat to X degrees (smart thermostat available)
    a) Brain asks if this is a permenant change or just for today, then performs action
    b) Brain performs action, then asks if this is a permenant change or just for today
    c) Brain warns user that the temp is outside of the normal comfort range, and asks if that's what they want. People misspeak. If the user asks to set the temp to 100F, the brain should push back
    d) Brain informs user that the thermostat doesn't support/allow that temp
    e) Brain warns user that the temp will increase utility costs dramatically, either before or after setting the temp, when appropriate. Ex: Set temp to 68F when the temp outside is 100F
    f) Brain warns user that the door is open and should be closed before turning on heat/ac

2.  User asks who is at the door (doorbell cam available)
    a)  Brain attempts to detect if someone is at the door and who they might be.
        - X is at the door
        - Mail carrier is at the door
        - A package is at the door
        - An unknown person is at the door
        - It looks like a solicitor is at the door
        - No one is at the door. Are you having a psychotic break?

3.  User asks to turn on the lights in X room
    a) Brain attempts to turn on those lights and informs the user of result

4.  User asks if the door is locked (smart lock available)
    a) Brain checks lock status, and replies
    b) Brain asks which door they want to check (clarifying question)
    c) Brain gives status of each door with a smart lock

5.  User asks how much longer before the oven is up to temp (smart oven)
    a) Brain checks current oven temp and target temp, calculates time to target, informs user
    b) Brain informs the user that the oven isn't on OR the oven is not responding

6.  User asks if the wash is done yet (smart washer)
    a) Brain checks washer status. If done, inform user. If not done, check time to completion, and informs user
    b) Brain informs user the washer isn't available

## Home Environment - Proactive
1.  Brain notices the temp is above/below the user's comfort zone
    a) sets temp within the comfort zone based on assessment of user preferences
        - If temp difference between indoors and outdoors is extreme, this would greatly impact utility costs
        - Users tolerance for small deviations to discomfort

2.  Brain notices people approaching the door
    a) Brain notifies user

3.  Brain notices a car pull into the driveway and sit there
    a) notifies user
    b) activates machine gun turrets and opens fire

4.  Brain notices an email arrives with critical information for the user
    a)  alert the user
    b)  extremely critical might warrant a text or bypassing normal restrictions
        - checking account overdraft may warrant alerting during a restricted notification period
        - sensitivity of information should affect communication style. Don't speak an alert of potentially embarassing info or give sensitive info verbally (like SSN) as others could overhear it

5.  Washer finishes while user is in another room
    a)  alert user

6.  Power is lost and comes back on at midnight. User is not at home
    a)  Turn off lights
    b)  Turn on heater in plant room
    c)  Turn on humidifier
