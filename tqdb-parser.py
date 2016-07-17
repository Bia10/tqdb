import json
import glob
import pprint
import re
import argparse
import os
import subprocess

from dbr_parser import *

#Parse command line call 
#TODO: Checking arguments for validity
parser = argparse.ArgumentParser(description='Parse all TitanQuest equipment from an extracted database.arz folder into a single JSON equipment_file.')
parser.add_argument('dir', type=str, help='Directory that the database.arz is extracted to')
parser.add_argument('-rarity', type=str, default='Rare,Epic,Legendary', help='Comma separated list of the possible rarities: Rare,Epic,Legendary')
parser.add_argument('-bitmap', type=str, help='Directory that the item textures are extracted to')
args = parser.parse_args()
db_dir = os.path.join(args.dir, '')
rarity = args.rarity.split(',')
bmp_dir = os.path.join(args.bitmap, '') if args.bitmap else ''

#Load the equipment files
equipment_files 	 = glob.glob(db_dir + "\\records\\item\\equipment*\\**\\*.dbr", recursive=True)
equipment_files.extend(glob.glob(db_dir + "\\records\\xpack\\item\\equipment*\\**\\*.dbr", recursive=True))

#Load the relic files
relic_files 	 = glob.glob(db_dir + "\\records\\item\\relics\\*.dbr")
relic_files.extend(glob.glob(db_dir + "\\records\\xpack\\item\\relics\\*.dbr"))
relic_files.extend(glob.glob(db_dir + "\\records\\item\\animalrelics\\*.dbr"))
relic_files.extend(glob.glob(db_dir + "\\records\\xpack\\item\\charms\\*.dbr"))

#Difficulties for relics:
difficulties = ["Normal", "Epic", "Legendary"]
requirements = ["Strength", "Dexterity", "Intelligence", "Level"]

#Load the tags
with open('tags.json', 'r') as tags_file:
	tags = json.load(tags_file)

items = dict()
for equipment_file in equipment_files: 
	with open(equipment_file) as equipment:
		#DBR file into a list of lines
		lines = [line.rstrip(',\n') for line in equipment]

		#Parse line into a dictionary of key, value properties:
		item_properties = dict([(k,v) for k,v in (dict(properties.split(',') for properties in lines)).items()  if has_numeric_value(v)])	

		#Check required keys:
		if not all(k in item_properties for k in ("itemNameTag", "itemLevel")):
			continue;

		#Filter on rarity:
		if not rarity:
			rarity = ['Rare', 'Epic', 'Legendary']

		if('itemClassification' not in item_properties or ('itemClassification' in item_properties and item_properties['itemClassification'] not in rarity)):
			continue

		new_item = dict()
		new_item['tag'] = item_properties['itemNameTag']
		new_item['name'] = tags[item_properties['itemNameTag']]
		new_item['level'] = item_properties['itemLevel']
		new_item['classification'] = item_properties['itemClassification']
		new_item['properties'] = parse_properties(item_properties)

		if 'characterBaseAttackSpeedTag' in item_properties:
			new_item['attackSpeed'] = item_properties['characterBaseAttackSpeedTag'][len('CharacterAttackSpeed'):]


		#Parse pet bonuses:
		if 'petBonusName' in item_properties:
			#Open pet bonus file
			with open(db_dir + item_properties['petBonusName']) as pet_file:
				pet_lines = [line.rstrip(',\n') for line in pet_file]
				pet_properties = dict([(k,v) for k,v in (dict(properties.split(',') for properties in pet_lines)).items()  if has_numeric_value(v)])
				pet_bonus = parse_properties(pet_properties)
				new_item['properties']['petBonusName'] = pet_bonus

		#Grab the set DBR if it exists
		if 'itemSetName' in item_properties:
			#Open set file
			with open(db_dir + item_properties['itemSetName']) as set_file:
				set_lines = [line.rstrip(',\n') for line in set_file]
				set_properties = dict([(k,v) for k,v in (dict(properties.split(',') for properties in set_lines)).items()  if has_numeric_value(v)])
				new_item['set'] = set_properties['setName']

		#Calculate requirements where needed
		if 'itemCostName' in item_properties:
			cost_prefix = item_properties['Class'].split('_')[1];
			cost_prefix = cost_prefix[0:1].lower() + cost_prefix[1:]

			#Open cost file
			with open(db_dir + item_properties['itemCostName']) as cost_file:
				cost_lines = [line.rstrip(',\n') for line in cost_file]
				cost_properties = dict([(k,v) for k,v in (dict(properties.split(',') for properties in cost_lines)).items()  if has_numeric_value(v)])
				
				itemLevel = item_properties['itemLevel']

				for requirement in requirements:
					equation_prefix = cost_prefix + requirement + 'Equation'
					if(equation_prefix in cost_properties):
						equation = cost_properties[equation_prefix]

						#Set the possible parameters in the equation:
						totalAttCount = len(new_item['properties'])
						itemLevel = int(new_item['level'])
						new_item['requirement' + requirement] = round(eval(equation))

		if(item_properties['Class'] in items):
			items[item_properties['Class']].append(new_item)
		else:
			items[item_properties['Class']] = [new_item]

		#Check bitmap:
		if bmp_dir and 'bitmap' in item_properties:
			bitmap = str(bmp_dir + item_properties['bitmap'])
			command = ['textureviewer/TextureViewer.exe', bitmap, 'uibitmaps/' + new_item['tag'] + '.png']
			subprocess.run(command)

for relic_file in relic_files:
	with open(relic_file) as relic:
		#DBR file into a list of lines
		lines = [line.rstrip(',\n') for line in relic]

		#Parse line into a dictionary of key, value properties:
		item_properties = dict([(k,v) for k,v in (dict(properties.split(',') for properties in lines)).items()  if has_numeric_value(v)])

		#Parse the difficulty and act from the filename:
		file_meta = os.path.basename(relic_file).split('_')

		new_item = dict()
		new_item['tag'] = item_properties['description']
		new_item['name'] = tags[item_properties['description']]
		new_item['description'] = tags[item_properties['itemText']]
		new_item['properties'] = parse_tiered_properties(item_properties)
		new_item['difficulty'] = difficulties[int(file_meta[0][1:]) - 1]
		new_item['act'] = file_meta[1]

		#Parse the possible completion bonuses:
		completion_bonuses = list()
		try:
			with open(db_dir + item_properties['bonusTableName']) as relic_bonus:
				relic_bonus_lines = [line.rstrip(',\n') for line in relic_bonus]
				relic_bonus_properties = dict([(k,v) for k,v in (dict(properties.split(',') for properties in relic_bonus_lines)).items()  if has_numeric_value(v)])

				bonuses = dict()
				weights = dict()
				for field, value in relic_bonus_properties.items():
					if 'randomizerName' in field:
						number = re.search(r'\d+', field).group()
						bonuses[number] = value
					if 'randomizerWeight' in field:
						number = re.search(r'\d+', field).group()
						weights[number] = int(value)

				total_weight = sum(weights.values())

				for field, value in bonuses.items():
					if field in weights:
						with open(db_dir + value) as bonus:
							bonus_lines = [line.rstrip(',\n') for line in bonus]
							bonus_properties = dict([(k,v) for k,v in (dict(properties.split(',') for properties in bonus_lines)).items()  if has_numeric_value(v)])

							completion_bonus = dict()
							completion_bonus['chance'] = '{0:.2f}'.format((weights[field] / total_weight) * 100)
							completion_bonus['bonus'] = parse_properties(bonus_properties)

							completion_bonuses.append(completion_bonus)

				new_item['bonus'] = completion_bonuses
		except FileNotFoundError:
			new_item['bonus'] = []			

		if(item_properties['Class'] in items):
			items[item_properties['Class']].append(new_item)
		else:
			items[item_properties['Class']] = [new_item]	

		#Check bitmap:
		if bmp_dir and  'relicBitmap' in item_properties:
			bitmap = str(bmp_dir + item_properties['relicBitmap'])
			command = ['textureviewer/TextureViewer.exe', bitmap, 'uibitmaps/' + new_item['tag'] + '.png']
			subprocess.run(command)

with open('items.json', 'w') as items_file:
	json.dump(items, items_file)


# Pretty print all the properties for this item that exist:
#pp = pprint.PrettyPrinter()
#if('itemSkillName' in properties and 'duneraider_flamestrike.dbr' in properties['itemSkillName'].lower() ):
#if(properties['itemNameTag'] == 'tagUWeapon100'):
#for field, text in defensive_absolute.items():
	#field_prefix = 'defensive' + field
	#if (field_prefix + 'DurationModifier') in properties:
	#pp.pprint(dict([(k,v) for k,v in item.items() if has_numeric_value(v)]))		