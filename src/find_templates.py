import os
import sys
import yaml
import json
import argparse
import pandas as pd
import numpy as np
import dotenv
import gzip

# load environment variables
dotenv.load_dotenv()

sys.path.append(os.path.join(os.getcwd(), 'aizynthfinder'))
sys.path.append(os.path.join(os.getcwd(), 'CoPriNet'))

from analysis.aiz_pos_analyser import AizPosTemplateAnalyser
from route_finders.aizynthfinder import AizRouteFinder
from route_finders.postera import PosRouteFinder
from optimisation.scoring import Scorer


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the template analysis")
    parser.add_argument("--targets", help="The path to the actives file")
    parser.add_argument("--config", help="The path to the RetroMix configuration file")
    parser.add_argument("--nproc", type=int, help="The number of processes to use", default=1)
    parser.add_argument("--output", help="The path to the output directory")
    parser.add_argument("--scoring_type", help="The type of scoring to use", default='state', choices=['state', 'cost', 'coprinet', 'frequency'])
    args = parser.parse_args()
    
    # load the configuration file
    with open(args.config, 'r') as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
    
    # load actives
    with open(args.targets, 'r') as f:
        actives = f.readlines()
    actives = [x.strip() for x in actives]
   
    if args.scoring_type == 'cost': 
        stock = pd.read_hdf(config['stock'], 'table')
        stock_dict = {inchi: price for inchi, price in zip(stock['inchi_key'], stock['price'])}
        
    print("Loaded actives & configuration & stock.")
    
    if os.path.isfile(os.path.join(args.output, 'aiz_routes.hdf5')):
        aiz_routes = pd.read_hdf(os.path.join(args.output, 'aiz_routes.hdf5'), 'table')
    else:      
        # load the route finders
        aiz_routes = AizRouteFinder(
            configfile = config['aizynthfinder_config'],
            nproc=args.nproc,
            smiles=actives
        ).find_routes()
        aiz_routes.to_hdf(os.path.join(args.output, 'aiz_routes.hdf5'), 'table')
    
    if os.path.isfile(os.path.join(args.output, 'pos_routes_aiz_format.json')):
        with open(os.path.join(args.output, 'pos_routes_aiz_format.json'), 'r') as f:
            pos_routes = json.load(f)
    else:      
        pos_routes = PosRouteFinder(
            smiles=actives,
            output=args.output,
            api_key=os.getenv('POSTERA_API_KEY')
        ).find_routes()

        
    with gzip.open(config['template_library'], 'r') as f:
        templates = pd.read_csv(f, sep='\t')
        
    canonical_template_library = templates['canonical_smarts'].tolist()
    
    # template analysis
    analyser = AizPosTemplateAnalyser(
        template_library=canonical_template_library,
        stock = stock_dict,
        scoring_type=args.scoring_type,
    )
    
    popular_templates = analyser.find_popular_templates(aiz_routes)
    with open(os.path.join(args.output, f'popular_templates.json'), 'w') as f:
        json.dump(popular_templates, f, indent=4)
    
    unused_templates = analyser.find_unused_templates(aiz_routes, pos_routes)
    with open(os.path.join(args.output, f'unused_templates.json'), 'w') as f:
        json.dump(unused_templates, f, indent=4)
    
    overlooked_templates, novel_templates = analyser.find_novel_overlooked_templates(unused_templates)        
    with open(os.path.join(args.output, f'overlooked_templates.json'), 'w') as f:
        json.dump(overlooked_templates, f, indent=4)
        
    with open(os.path.join(args.output, f'novel_templates.json'), 'w') as f:
        json.dump(novel_templates, f, indent=4)
        
    print("Analysis complete.")
    
    

