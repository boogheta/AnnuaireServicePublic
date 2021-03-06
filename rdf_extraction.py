# -*- coding: utf-8 -*-
"""
@author: Alexis Eidelman

Travaille sur les données issues de 
https://www.data.gouv.fr/fr/datasets/
service-public-fr-annuaire-de-ladministration-base-de-donnees-nationales/

pour obtenir le graph des administrations
Il y a 223874 triplets
7336 entités

"""

import os
import json
import rdflib
import pandas as pd
import networkx as nx


def all_triplets(g):
    ''' la requete de tous les triplets '''
    DF = rdflib.Namespace('http://www.df.gouv.fr/administration_francaise/annuaire#')
    requete =  g.query("""SELECT ?a ?b ?c
        WHERE {?a ?b ?c }""", 
        initNs={ 'df': DF })
    return requete


def triplets_to_dict(data):
    # pour simplifier l'écriture
    df = 'http://www.df.gouv.fr/administration_francaise/annuaire#'
    ann = 'http://lannuaire.service-public.fr/'
    # crée un dictionnaire 
    diction = dict()
    for row in data:
        index = row[0].toPython()
        index = index.replace(df, 'df/').replace(ann, 'an/')
        predicat = row[1].toPython().replace(df, 'df/').replace(ann, 'an/')
        attribut = row[2].toPython()
        if isinstance(attribut, str):
            attribut = attribut.replace(df, 'df/').replace(ann, 'an/')
        if index not in diction:
            diction[index] = dict()
        diction[index][predicat] = attribut
    return diction


def _notnull_columns(tab):
    ''' retourne les variables qui ont des 
    valeurs non nulles '''
    nb_notnull = tab.notnull().sum()
    cols_notnull = nb_notnull[nb_notnull > 0]
    return cols_notnull.index.tolist()


def _only_notnull_columns(tab):
    ''' table sans les colonnes entierement nulles '''
    return tab[_notnull_columns(tab)]


def find_association(tab):
    ''' recupere les triplets avec un lien parent/enfant '''
    type_ = tab["http://www.w3.org/1999/02/22-rdf-syntax-ns#type"]

    # certaines lignes correspondent à des associations :
    association = tab[type_ == 'http://www.mondeca.com/system/t3#BN']    
    association = _only_notnull_columns(association)
    # en gros, nt, Narrower Term c'est l'enfant
    # bt, Broader Term, c'est le parent
    association.rename(columns={
        'http://www.mondeca.com/system/t3#bt': 'parent',
        'http://www.mondeca.com/system/t3#nt': 'enfant',
        },
        inplace=True)
    
    # il y a aussi les autres hiérarchies
    AutreHierarchie = tab[type_ == 'df/AutreHierarchie']
    AutreHierarchie = _only_notnull_columns(AutreHierarchie)
    AutreHierarchie.rename(columns={
        'df/serviceFils': 'enfant',
        'df/servicePere': 'parent',
        },
        inplace=True)    
    
    return AutreHierarchie.append(association)


def recursive_run(G, item, dico_values):
    ''' crée un dictionnaire à partir d'un Graph '''
    children = [recursive_run(G, el, G[item][el]) 
                for el in G.successors_iter(item)]
    dico_values['name'] = item
    if len(children) != 0:
        dico_values['children'] = children
    return dico_values


def tree_from_df(tab_avec_liens):
    G = nx.Graph()
    variables_fiche = ['http://www.w3.org/2000/01/rdf-schema#label',
                       'df/sigle']
    tab_avec_liens['parent'].fillna('source', inplace=True)
    usefull = tab_avec_liens[variables_fiche + ['parent', 'index']]
    usefull.columns = ['label', 'sigle', 'parent', 'index']
    
    usefull['sigle'].fillna('nc.', inplace=True)
    usefull['label'].fillna('nc.', inplace=True)
    
    G = nx.from_pandas_dataframe(
        usefull, 
        'parent', 'index', ['label', 'sigle'],
        nx.DiGraph()
        )
    
    tree = recursive_run(G, 'source', dict())
    tree['label'] = 'source'
    return tree


def stat(tab, tab2):
    len(tab) # 13877 lignes
    len(tab.columns) # 50 colonnes = 50 prédicats différents
    ## propriété de la table
    tab.isnull().sum()
    for col in tab.columns:
        print(tab[col].value_counts().head(3))
    # il y a 3 doublons : tab.duplicated().sum()

    #, 'df/Ministere',
    # à df/ministère correspondent les département et des entités
    # qui existe par ailleurs. On peu supprimer
    # qui sont le 13 qui n'ont pas de parent ? c'et :
    tab2[tab2._merge == 'left_only']
    type_entity = tab2["http://www.w3.org/1999/02/22-rdf-syntax-ns#type"]
    # TODO: regarde les départements
    tab2[type_entity == 'df/Ministere']
    tab2[~tab2['http://www.w3.org/2000/01/rdf-schema#label'].str.contains('<< Dép.')]
    # => on retire 101 lignes


def rdf_extraction(name):
    g = rdflib.Graph()
    origin_file = os.path.join('data', name + '.rdf')
    g.parse(origin_file, format='xml')
    data = all_triplets(g)
    diction = triplets_to_dict(data)
    tab = pd.DataFrame.from_dict(diction).T
    tab.drop_duplicates(inplace=True)
    assoc = find_association(tab)
    # on ne garde que certain types peut probablement retirer ces éléments :
    type_entity = tab["http://www.w3.org/1999/02/22-rdf-syntax-ns#type"]
    tab_entities = tab[type_entity == 'an/ServiceRAF'].reset_index()
    # on reset index parce que l'on veut conserver ça pendant le merge
    
    tab_avec_liens = tab_entities.merge(assoc,
        left_on='index',
        right_on='enfant',
        how='left',
        suffixes=('','_lien'),
        indicator=True)
    tab_avec_liens.sort(['index', 'parent'], inplace=True)
    
    tree = tree_from_df(tab_avec_liens)
    json_name = os.path.join('json', name + '.json')
    csv_name = os.path.join('csv', name + '.csv')
    with open(json_name, 'w') as outfile:
        json.dump(tree, outfile, indent=2, sort_keys=True)
    
    tab_avec_liens.to_csv(csv_name, index=False)

## test
#rdf_extraction('annuaire_gouv')