# the comments only needed if you use a virtual environment
#. /path/to/your/venv/bin/activate

nest_conf_folder="custom_configs"

# Grab Event Pokemons from Serebii and Update Config

event_list=$(curl -s https://www.serebii.net/pokemongo/events/ultrabonusevent2019part1.shtml|grep -A30000 'Spawn Increases In Event'|grep -B30000 'Specific Egg'|grep \#|sed -e ':a;N;$!ba;s/\n//g' -e 's,\#,,g' -e 's,\t,,g' -e 's|\r|,|g' -e 's|,$||')

sed -i s/EVENT_POKEMON.*/"EVENT_POKEMON = [$event_list]"/g default.ini

# Go Through custom configs and start Nest Discovery

for nest_conf in "$nest_conf_folder"/*
do
  echo $nest_conf
  python analyze_nests.py -c $nest_conf
done

#deactivate
