import json
import re
from collections import Counter, defaultdict
from typing import Dict, List, Tuple, Optional

# ==================== CONFIGURATION ====================

# Mapping des institutions connues vers leurs pays
INSTITUTION_COUNTRY_MAP = {
    # Algérie
    'Mouloud Mammeri University': 'Algeria',
    'University of Algiers': 'Algeria',
    'University of Boumerdes': 'Algeria',
    'University Frères Mentouri': 'Algeria',
    'Université Larbi Tébessi': 'Algeria',
    'University of Sciences and Technology Houari Boumediene': 'Algeria',
    'USTHB': 'Algeria',
    'Larbi Ben M\'hidi University': 'Algeria',
    'Université Oran': 'Algeria',
    'University of Skikda': 'Algeria',
    'University Ferhat Abbas': 'Algeria',
    'University of Laghouat': 'Algeria',
    'Badji Mokhtar-Annaba University': 'Algeria',
    'University of Béjaïa': 'Algeria',
    'University of Ouargla': 'Algeria',
    'University of Abou Bekr Belkaïd': 'Algeria',
    'Université de Mostaganem': 'Algeria',
    'University of Blida': 'Algeria',
    'Université IBN Khaldoun Tiaret': 'Algeria',
    'University of Batna': 'Algeria',
    'Université Constantine': 'Algeria',
    'University Mohamed Boudiaf': 'Algeria',
    'Mohamed-Cherif Messaadia University': 'Algeria',
    'University of Bechar': 'Algeria',
    'University of Biskra': 'Algeria',
    'University of Jijel': 'Algeria',
    'Hassiba Benbouali University': 'Algeria',
    'University of Guelma': 'Algeria',
    'University of Eloued': 'Algeria',
    'University of Ghardaia': 'Algeria',
    'University Yahia Fares': 'Algeria',
    'Université Djilali de Sidi Bel Abbès': 'Algeria',
    'Université Mustapha Stambouli de Mascara': 'Algeria',
    'Ziane Achour University': 'Algeria',
    'University Ahmed Zabana': 'Algeria',
    'Abbès Laghrour University': 'Algeria',
    'Université de Saida': 'Algeria',
    'Université de ain Témouchent': 'Algeria',
    'Ahmed Draia University': 'Algeria',
    'Tissemsilt University': 'Algeria',
    'University of Tamanghasset': 'Algeria',
    'Centre Universitaire de Mila': 'Algeria',
    'Polytechnic School of Algiers': 'Algeria',
    'École Nationale Polytechnique': 'Algeria',
    'École Normale Supérieure': 'Algeria',
    'Higher National Veterinary School': 'Algeria',
    'National Higher School of Statistics': 'Algeria',
    'CERIST': 'Algeria',
    'CRSTRA': 'Algeria',
    'CDTA': 'Algeria',
    'CRND': 'Algeria',
    'CRAAG': 'Algeria',
    'Sonatrach': 'Algeria',
    'NEAL': 'Algeria',
    
    # France
    'Université de Strasbourg': 'France',
    'Université Paris': 'France',
    'Sorbonne': 'France',
    'CNRS': 'France',
    'INRIA': 'France',
    'INSERM': 'France',
    'Université Claude Bernard': 'France',
    'Université d\'Orléans': 'France',
    'Université de Technologie de Troyes': 'France',
    'Université de Pau': 'France',
    'CY Cergy Paris Université': 'France',
    'Arts et Métiers': 'France',
    'École Polytechnique': 'France',
    'Mines Paris': 'France',
    'CentraleSupélec': 'France',
    
    # USA / Canada
    'University of Pennsylvania': 'USA',
    'West Virginia University': 'USA',
    'St. Jude': 'USA',
    'New York University': 'USA',
    'University of Manitoba': 'Canada',
    'Université du Québec': 'Canada',
    'University of Sherbrooke': 'Canada',
    
    # Europe
    'Real Academia Española': 'Spain',
    'Universidad San Pablo': 'Spain',
    'Universitat de Barcelona': 'Spain',
    'University of Liège': 'Belgium',
    'University of Coimbra': 'Portugal',
    'University of Trento': 'Italy',
    'University of Bari': 'Italy',
    'University of Brescia': 'Italy',
    'Università di Camerino': 'Italy',
    'University of Duisburg-Essen': 'Germany',
    'Max Planck Institute': 'Germany',
    'Helmholtz Institute': 'Germany',
    'Deutsches Zentrum für Luft- und Raumfahrt': 'Germany',
    'Aalborg University': 'Denmark',
    'Aarhus University': 'Denmark',
    'Aalto University': 'Finland',
    'Norwegian Biodiversity Information Centre': 'Norway',
    'Luleå University of Technology': 'Sweden',
    'Kristianstad University': 'Sweden',
    'University of Belgrade': 'Serbia',
    'Ovidius University': 'Romania',
    'Silesian University of Technology': 'Poland',
    'Adam Mickiewicz University': 'Poland',
    
    # UK
    'University of Oxford': 'UK',
    'University of Cambridge': 'UK',
    'Imperial College': 'UK',
    'University College London': 'UK',
    'Cranfield University': 'UK',
    'WRc': 'UK',
    'Art UK': 'UK',
    
    # Afrique
    'University of Cape Town': 'South Africa',
    'University of Sousse': 'Tunisia',
    'Tunis University': 'Tunisia',
    'University of Sfax': 'Tunisia',
    'Abdelmalek Essaâdi University': 'Morocco',
    'Mohammed V University': 'Morocco',
    'Ain Shams University': 'Egypt',
    'Suez Canal University': 'Egypt',
    'Beni-Suef University': 'Egypt',
    'Mansoura University': 'Egypt',
    'University of Ibadan': 'Nigeria',
    'University of Nairobi': 'Kenya',
    'Technical University of Kenya': 'Kenya',
    'University of Dar es Salaam': 'Tanzania',
    
    # Moyen-Orient
    'King Abdullah University': 'Saudi Arabia',
    'King Fahd University': 'Saudi Arabia',
    'Prince Sattam Bin Abdulaziz University': 'Saudi Arabia',
    'Umm al-Qura University': 'Saudi Arabia',
    'Qassim University': 'Saudi Arabia',
    'Najran University': 'Saudi Arabia',
    'United Arab Emirates University': 'UAE',
    'New York University Abu Dhabi': 'UAE',
    'University of Kerbala': 'Iraq',
    'University of Baghdad': 'Iraq',
    'University of Basrah': 'Iraq',
    'University of Wasit': 'Iraq',
    'University Of Fallujah': 'Iraq',
    'Sana\'a University': 'Yemen',
    'University of Ha\'il': 'Saudi Arabia',
    'Sultan Zainal Abidin University': 'Malaysia',
    'Technical University of Malaysia': 'Malaysia',
    'INTI International University': 'Malaysia',
    
    # Asie
    'Beijing Institute of Technology': 'China',
    'Beijing Language and Culture University': 'China',
    'Southeast University': 'China',
    'Northwestern Polytechnical University': 'China',
    'Nanjing University': 'China',
    'Wuhan Textile University': 'China',
    'Shaoxing University': 'China',
    'Shantou University': 'China',
    'Jamia Millia Islamia': 'India',
    'Central University of Haryana': 'India',
    'University of Madras': 'India',
    'Magadh University': 'India',
    'Haldia Institute of Technology': 'India',
    'Daffodil International University': 'Bangladesh',
    'Balochistan University': 'Pakistan',
    'Abdul Wali Khan University': 'Pakistan',
    'Islamia College University': 'Pakistan',
    'Khazar University': 'Azerbaijan',
    'Termez State University': 'Uzbekistan',
    
    # Amérique du Sud
    'Universidade Federal da Paraíba': 'Brazil',
    'Universidad Autónoma de Guerrero': 'Mexico',
    'Instituto de Ciencia y Tecnología': 'Spain',
    
    # Océanie
    'Diponegoro University': 'Indonesia',
    'Universitas Sumatera Utara': 'Indonesia',
    'Universitas 17 Agustus 1945': 'Indonesia',
}

# Mots-clés par pays
COUNTRY_KEYWORDS = {
    'Algeria': ['algeria', 'algérie', 'alger', 'algiers', 'oran', 'constantine', 'annaba', 'blida', 
                'béjaïa', 'tlemcen', 'sétif', 'batna', 'biskra', 'tizi-ouzou', 'boumerdes', 'chlef',
                'mostaganem', 'tiaret', 'mascara', 'sidi bel abbès', 'skikda', 'guelma', 'jijel',
                'laghouat', 'ouargla', 'béchar', 'tamanrasset', 'el oued', 'ghardaïa', 'adrar',
                'tébessa', 'bordj bou arreridj', 'm\'sila', 'khenchela', 'souk ahras', 'tipaza',
                'mila', 'aïn defla', 'naâma', 'aïn témouchent', 'reli'],
    'France': ['france', 'paris', 'lyon', 'marseille', 'toulouse', 'bordeaux', 'lille', 'nantes',
               'strasbourg', 'montpellier', 'rennes', 'grenoble', 'nice', 'toulon', 'cnrs', 'inria',
               'inserm', 'cea', 'sorbonne', 'saclay', 'polytechnique', 'centrale', 'mines'],
    'USA': ['usa', 'united states', 'america', 'california', 'new york', 'texas', 'florida',
            'pennsylvania', 'massachusetts', 'illinois', 'ohio', 'michigan', 'washington', 'boston',
            'chicago', 'stanford', 'harvard', 'mit', 'berkeley', 'princeton', 'yale', 'columbia'],
    'UK': ['uk', 'united kingdom', 'england', 'britain', 'london', 'cambridge', 'oxford',
           'manchester', 'edinburgh', 'glasgow', 'birmingham', 'leeds', 'liverpool', 'bristol',
           'sheffield', 'nottingham', 'southampton', 'cardiff', 'belfast', 'imperial', 'ucl'],
    'Canada': ['canada', 'quebec', 'ontario', 'toronto', 'montreal', 'vancouver', 'ottawa',
               'calgary', 'edmonton', 'sherbrooke', 'manitoba', 'alberta', 'british columbia',
               'mcgill', 'waterloo', 'ubc'],
    'Germany': ['germany', 'deutschland', 'berlin', 'munich', 'hamburg', 'frankfurt', 'stuttgart',
                'cologne', 'dresden', 'leipzig', 'heidelberg', 'bonn', 'aachen', 'max planck',
                'fraunhofer', 'helmholtz'],
    'Italy': ['italy', 'italia', 'rome', 'milan', 'naples', 'turin', 'florence', 'bologna',
              'venice', 'genoa', 'pisa', 'padua', 'bari', 'brescia', 'camerino', 'politecnico'],
    'Spain': ['spain', 'españa', 'madrid', 'barcelona', 'valencia', 'seville', 'bilbao',
              'zaragoza', 'málaga', 'granada', 'santiago', 'salamanca', 'real academia'],
    'Tunisia': ['tunisia', 'tunisie', 'tunis', 'sousse', 'sfax', 'gabès', 'kairouan', 'bizerte',
                'monastir', 'nabeul'],
    'Morocco': ['morocco', 'maroc', 'rabat', 'casablanca', 'marrakech', 'fès', 'tanger', 'agadir',
                'meknès', 'oujda', 'tétouan', 'essaâdi'],
    'Egypt': ['egypt', 'égypte', 'cairo', 'alexandria', 'giza', 'suez', 'mansoura', 'assiut',
              'ain shams', 'beni-suef'],
    'Saudi Arabia': ['saudi', 'saoudite', 'riyadh', 'jeddah', 'mecca', 'medina', 'dammam',
                     'qassim', 'najran', 'umm al-qura', 'king abdullah', 'king fahd', 'kfu'],
    'UAE': ['uae', 'emirates', 'émirats', 'dubai', 'abu dhabi', 'sharjah', 'ajman'],
    'Belgium': ['belgium', 'belgique', 'brussels', 'antwerp', 'ghent', 'liège', 'leuven',
                'louvain', 'vrije universiteit'],
    'Switzerland': ['switzerland', 'suisse', 'zurich', 'geneva', 'basel', 'bern', 'lausanne',
                    'eth', 'epfl', 'nestlé'],
    'Netherlands': ['netherlands', 'holland', 'amsterdam', 'rotterdam', 'utrecht', 'leiden',
                    'groningen', 'delft', 'eindhoven', 'wageningen'],
    'Sweden': ['sweden', 'stockholm', 'gothenburg', 'uppsala', 'lund', 'luleå', 'kristianstad',
               'karolinska', 'chalmers'],
    'Norway': ['norway', 'oslo', 'bergen', 'trondheim', 'stavanger', 'tromsø', 'ntnu'],
    'Denmark': ['denmark', 'copenhagen', 'aarhus', 'aalborg', 'odense', 'dtu'],
    'Finland': ['finland', 'helsinki', 'espoo', 'tampere', 'turku', 'oulu', 'aalto'],
    'Japan': ['japan', 'tokyo', 'osaka', 'kyoto', 'nagoya', 'sapporo', 'fukuoka', 'tohoku',
              'tsukuba', 'keio', 'waseda'],
    'China': ['china', 'beijing', 'shanghai', 'guangzhou', 'shenzhen', 'wuhan', 'nanjing',
              'xian', 'tianjin', 'chongqing', 'tsinghua', 'peking', 'fudan', 'zhejiang'],
    'India': ['india', 'delhi', 'mumbai', 'bangalore', 'chennai', 'kolkata', 'hyderabad',
              'pune', 'ahmedabad', 'iit', 'nit', 'jamia millia', 'haryana', 'madras'],
    'Australia': ['australia', 'sydney', 'melbourne', 'brisbane', 'perth', 'adelaide',
                  'canberra', 'unsw', 'monash', 'queensland', 'anu'],
    'Brazil': ['brazil', 'brasil', 'são paulo', 'rio de janeiro', 'brasília', 'paraíba',
               'usp', 'unicamp', 'ufrj'],
    'South Africa': ['south africa', 'cape town', 'johannesburg', 'pretoria', 'durban',
                     'stellenbosch', 'wits'],
    'Malaysia': ['malaysia', 'kuala lumpur', 'penang', 'johor', 'malacca', 'sultan zainal',
                 'inti', 'utm', 'ukm'],
    'Indonesia': ['indonesia', 'jakarta', 'surabaya', 'bandung', 'yogyakarta', 'diponegoro'],
    'Pakistan': ['pakistan', 'islamabad', 'karachi', 'lahore', 'peshawar', 'quetta',
                 'balochistan', 'islamia college'],
    'Iraq': ['iraq', 'baghdad', 'basrah', 'mosul', 'karbala', 'najaf', 'fallujah', 'wasit'],
}

# ==================== FONCTIONS D'ANALYSE ====================

def extract_country_from_affiliation(affiliation: str) -> Optional[str]:
    """
    Détecte le pays à partir d'une affiliation
    """
    if not affiliation:
        return None
    
    aff_lower = affiliation.lower()
    
    # 1. Chercher dans le mapping des institutions connues
    for institution, country in INSTITUTION_COUNTRY_MAP.items():
        if institution.lower() in aff_lower:
            return country
    
    # 2. Chercher par mots-clés de pays
    for country, keywords in COUNTRY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in aff_lower:
                return country
    
    # 3. Chercher des patterns explicites "Pays" ou "Country"
    country_patterns = [
        r'(?:^|,\s*)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*$',  # Dernier élément après virgule
        r'\(([^)]+)\)',  # Entre parenthèses
    ]
    
    for pattern in country_patterns:
        match = re.search(pattern, affiliation)
        if match:
            potential_country = match.group(1).strip()
            # Vérifier si c'est un pays connu
            for country, keywords in COUNTRY_KEYWORDS.items():
                if any(kw in potential_country.lower() for kw in keywords):
                    return country
    
    # 4. Détection spécifique pour l'Algérie (wilayas)
    algerian_wilayas = ['adrar', 'chlef', 'laghouat', 'oum el bouaghi', 'batna', 'béjaïa',
                        'biskra', 'béchar', 'blida', 'bouira', 'tamanrasset', 'tébessa',
                        'tlemcen', 'tiaret', 'tizi ouzou', 'alger', 'djelfa', 'jijel',
                        'sétif', 'saïda', 'skikda', 'sidi bel abbès', 'annaba', 'guelma',
                        'constantine', 'médéa', 'mostaganem', 'm\'sila', 'mascara', 'ouargla',
                        'oran', 'el bayadh', 'illizi', 'bordj bou arreridj', 'boumerdès',
                        'el tarf', 'tindouf', 'tissemsilt', 'el oued', 'khenchela', 'souk ahras',
                        'tipaza', 'mila', 'aïn defla', 'naâma', 'aïn témouchent', 'ghardaïa',
                        'reli']
    
    for wilaya in algerian_wilayas:
        if wilaya in aff_lower:
            return 'Algeria'
    
    return 'Unknown'

def analyze_affiliations(json_file_path: str):
    """
    Analyse complète des affiliations depuis un fichier JSON
    """
    print("=" * 80)
    print("ANALYSE GÉOGRAPHIQUE DES AFFILIATIONS")
    print("=" * 80)
    
    # Charger le JSON
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"\n📊 Total co-auteurs analysés : {len(data)}")
    
    # Statistiques par pays
    country_stats = defaultdict(lambda: {'count': 0, 'affiliations': [], 'institutions': Counter()})
    unknown_affiliations = []
    
    for item in data:
        affiliation = item.get('affiliation_at_time', '')
        if not affiliation:
            continue
        
        country = extract_country_from_affiliation(affiliation)
        country_stats[country]['count'] += 1
        country_stats[country]['affiliations'].append(affiliation)
        
        # Extraire l'institution (première partie avant la virgule)
        institution = affiliation.split(',')[0].strip()
        country_stats[country]['institutions'][institution] += 1
    
    # Afficher les résultats
    print("\n🌍 DISTRIBUTION PAR PAYS")
    print("-" * 60)
    
    sorted_countries = sorted(country_stats.items(), key=lambda x: x[1]['count'], reverse=True)
    
    total_with_country = sum(stats['count'] for country, stats in country_stats.items() if country != 'Unknown')
    
    for country, stats in sorted_countries:
        count = stats['count']
        percentage = (count / len(data)) * 100
        
        if country == 'Unknown':
            print(f"\n❓ {country}: {count} ({percentage:.1f}%)")
        else:
            print(f"✅ {country}: {count} ({percentage:.1f}%)")
    
    # Top institutions par pays
    print("\n🏛️ TOP INSTITUTIONS PAR PAYS")
    print("-" * 60)
    
    for country, stats in sorted_countries:
        if country == 'Unknown' or stats['count'] < 5:
            continue
        
        print(f"\n📍 {country} (Total: {stats['count']})")
        for institution, inst_count in stats['institutions'].most_common(10):
            print(f"   - {institution}: {inst_count}")
    
    # Affiliations non reconnues (échantillon)
    print("\n🔍 ÉCHANTILLON D'AFFILIATIONS NON RECONNUES")
    print("-" * 60)
    
    unknown_sample = unknown_affiliations[:20] if unknown_affiliations else country_stats['Unknown']['affiliations'][:20]
    for aff in unknown_sample:
        print(f"   - {aff}")
    
    # Statistiques globales
    print("\n📈 STATISTIQUES GLOBALES")
    print("-" * 60)
    print(f"Total affiliations analysées : {len(data)}")
    print(f"Pays détectés : {len([c for c in country_stats if c != 'Unknown'])}")
    print(f"Affiliations avec pays identifié : {total_with_country} ({(total_with_country/len(data))*100:.1f}%)")
    print(f"Affiliations non identifiées : {country_stats['Unknown']['count']} ({(country_stats['Unknown']['count']/len(data))*100:.1f}%)")
    
    # Export des résultats
    export_results(country_stats, len(data))
    
    return country_stats

def export_results(country_stats: Dict, total: int):
    """
    Exporte les résultats en JSON et CSV
    """
    # Export JSON
    export_data = {
        'total_affiliations': total,
        'countries_detected': len([c for c in country_stats if c != 'Unknown']),
        'country_distribution': {
            country: {
                'count': stats['count'],
                'percentage': round((stats['count'] / total) * 100, 2),
                'top_institutions': dict(stats['institutions'].most_common(10))
            }
            for country, stats in country_stats.items()
        }
    }
    
    with open('geographic_analysis.json', 'w', encoding='utf-8') as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Résultats exportés dans geographic_analysis.json")
    
    # Export CSV des pays
    import csv
    with open('country_distribution.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Country', 'Count', 'Percentage'])
        
        for country, stats in sorted(country_stats.items(), key=lambda x: x[1]['count'], reverse=True):
            writer.writerow([country, stats['count'], f"{(stats['count']/total)*100:.2f}%"])
    
    print(f"✅ Distribution par pays exportée dans country_distribution.csv")

# ==================== EXÉCUTION ====================

if __name__ == '__main__':
    # Spécifiez le chemin vers votre fichier JSON
    json_file = 'affiliations_sample.json'  # Changez ce nom
    
    try:
        results = analyze_affiliations(json_file)
        print("\n✨ Analyse terminée avec succès !")
    except FileNotFoundError:
        print(f"❌ Fichier {json_file} non trouvé.")
        print("Placez votre fichier JSON dans le même dossier que ce script.")
    except Exception as e:
        print(f"❌ Erreur : {e}")


        