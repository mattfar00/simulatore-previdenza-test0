import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np

# ---------------------------------------------------------------------------
# CONFIGURAZIONE PAGINA
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Simulatore Previdenziale Pro", layout="wide")
st.title("🚀 Confronto Previdenziale: Fondo vs PAC + TFR")

# ---------------------------------------------------------------------------
# DATI CCNL / FONDI NEGOZIALI (fonti: accordi CCNL, schede costi COVIP 2024/25)
# ---------------------------------------------------------------------------
CCNL_PRESET = {
    "Metalmeccanico (Cometa)": {
        "fondo": "Cometa",
        "contrib_lav_pct": 0.012,        # min 1,2% per avere contributo datore
        "contrib_azienda_pct": 0.020,    # 2,0% dei minimi
        "contrib_azienda_u35_pct": 0.022,# 2,2% under 35
        "tfr_pct": 0.0691,               # 6,91% RAL (quota TFR annua)
        "costo_iniziale": 5.16,
        "costo_fisso": 12.0,
        "mensilita": 13,
        "livelli": {
            "D1": 1784.94, "D2": 1979.37, "C1": 2022.12, "C2": 2064.88,
            "C3": 2211.43, "B1": 2370.33, "B2": 2542.98, "B3": 2838.99,
            "A1": 2907.01,
        },
        "scatto_valore": 30.0,   # €/mese medio per scatto
        "scatto_ogni_anni": 2,   # biennale
        "scatti_max": 5,
        "comparti": {
            # nome: (TER annuo, rend. medio atteso, volatilità, quota titoli Stato)
            # NB: gli "atteso/vol" sono assunzioni forward-looking del GBM. In
            # modalità bootstrap si usano invece i rendimenti storici reali.
            "Garantito":   (0.0040, 0.010, 0.030, 0.70),
            "Bilanciato":  (0.0020, 0.027, 0.070, 0.45),
            "Azionario":   (0.0025, 0.045, 0.135, 0.20),
            # Monetario Plus: params GBM stimati (storico: CAGR ~1,1% vol ~1,5%)
            "Monetario":   (0.0025, 0.012, 0.015, 0.80),
        },
    },
    "Commercio Confcommercio (Fon.Te)": {
        "fondo": "Fon.Te",
        "contrib_lav_pct": 0.0055,       # min 0,55%
        "contrib_azienda_pct": 0.0155,   # 1,55%
        "contrib_azienda_u35_pct": 0.0155,
        "tfr_pct": 0.0691,
        "costo_iniziale": 15.50,
        "costo_fisso": 22.0,
        "mensilita": 14,
        "livelli": {
            "Quadro": 2183.09, "I": 1966.54, "II": 1701.04, "III": 1453.94,
            "IV": 1257.46, "V": 1136.07, "VI": 1019.94, "VII": 873.22,
        },
        "scatti_valore_livello": {
            "Quadro": 30.0, "I": 27.0, "II": 25.0, "III": 22.0,
            "IV": 20.0, "V": 18.0, "VI": 16.0, "VII": 15.0,
        },
        "scatto_valore": 20.0,
        "scatto_ogni_anni": 3,
        "scatti_max": 5,
        "comparti": {
            "Conservativo":  (0.0050, 0.0133, 0.0281, 0.60),
            "Sviluppo":  (0.0045, 0.0241, 0.0503, 0.40),
            "Dinamico":  (0.0045, 0.0636, 0.0669, 0.25),
            "Crescita":  (0.0045, 0.0460, 0.0541, 0.15),
        },
    },
    "Commercio Conflavoro PMI (Fon.Te)": {
        "fondo": "Fon.Te",
        "contrib_lav_pct": 0.0055,       # min 0,55%
        "contrib_azienda_pct": 0.0155,   # 1,55%
        "contrib_azienda_u35_pct": 0.0155,
        "tfr_pct": 0.0691,
        "costo_iniziale": 15.50,
        "costo_fisso": 22.0,
        "mensilita": 14,
        "livelli": {
            "Quadro": 2986.95, "I": 2507.20, "II": 2236.65, "III": 1985.15,
            "IV": 1785.00, "V": 1662.00, "VI": 1543.05, "VII": 1399.35,
        },
        "scatti_valore_livello": {
            "Quadro": 26.0, "I": 25.0, "II": 23.0, "III": 22.0,
            "IV": 21.5, "V": 21.0, "VI": 20.5, "VII": 20.0,
        },
        "scatto_valore": 22.0,
        "scatto_ogni_anni": 3,
        "scatti_max": 10,
        "comparti": {
            "Conservativo":  (0.0050, 0.0133, 0.0281, 0.60),
            "Sviluppo":  (0.0045, 0.0241, 0.0503, 0.40),
            "Dinamico":  (0.0045, 0.0636, 0.0669, 0.25),
            "Crescita":  (0.0045, 0.0460, 0.0541, 0.15),
        },
    },
}

# ---------------------------------------------------------------------------
# STORICO RENDIMENTI ANNUI NETTI PER COMPARTO  (branch bootstrap — DA RIEMPIRE)
# ---------------------------------------------------------------------------
# ▸ Questo blocco alimenta la modalità "Bootstrap storico comparto".
# ▸ IMPORTANTE: le liste qui sotto sono VUOTE di proposito. Vanno riempite con
#   i rendimenti annui NETTI reali di ogni comparto (fonte: schede COVIP /
#   relazioni annuali del fondo — es. Cometa "Crescita/Reddito/Sicurezza",
#   Fon.Te "Dinamico/Bilanciato/Garantito"). Ogni valore è un rendimento annuo
#   in forma decimale (0.084 = +8,4%; -0.052 = -5,2%).
# ▸ Finché una lista resta vuota, la modalità bootstrap per quel comparto
#   ricade automaticamente sul GBM parametrico e mostra un avviso in app.
# ▸ NON sono stati inseriti numeri "di esempio": in uno strumento previdenziale
#   inventare una serie storica falserebbe il resampling. Inseriscili tu (o
#   chiedimi di recuperarli dalle schede COVIP).
STORICO_ANNUALE = {
    # Cometa — rendimenti annui NETTI per anno solare (Dic->Dic), calcolati
    # dalle quote mensili ufficiali del fondo. Fonte quote: tabelle Cometa.
    "Cometa": {
        # Sicurezza 2020 (2021-2025). Serie CORTA: solo 5 anni -> bootstrap poco
        # affidabile, l'app avvisa e resta comunque conservativa.
        "Garantito":  [0.01581, -0.12295, 0.05902, 0.02797, 0.02603],
        # Reddito (1999-2025)
        "Bilanciato": [0.03902, 0.03904, 0.00233, -0.02273, 0.04047, 0.03907,
                       0.06664, 0.02898, 0.02616, -0.03556, 0.07235, 0.03293,
                       0.01661, 0.07830, 0.04283, 0.08318, 0.01910, 0.02543,
                       0.02453, -0.03000, 0.06863, 0.01516, 0.03779, -0.10379,
                       0.06054, 0.05524, 0.05114],
        # Crescita (2006-2025)
        "Azionario":  [0.04819, 0.00886, -0.15674, 0.13717, 0.04147, -0.00247,
                       0.11428, 0.09616, 0.06918, 0.02237, 0.03715, 0.04845,
                       -0.04701, 0.11287, 0.00416, 0.05201, -0.12292, 0.10671,
                       0.10422, 0.07316],
        # Monetario Plus (2006-2025)
        "Monetario":  [0.02855, 0.02336, 0.02368, 0.02520, 0.00387, 0.01766,
                       0.02960, 0.01260, 0.01028, 0.00471, 0.00172, -0.00289,
                       -0.00552, 0.00395, 0.00511, -0.00309, -0.02902, 0.02904,
                       0.03098, 0.02235],
    },
    # Fon.Te — rendimenti annui netti (Dic->Dic) dalle quote ufficiali.
    "Fon.Te": {
        "Conservativo": [0.03875, 0.01064, 0.00982, 0.05741, 0.02611, 0.03845, 0.01797, 0.01062, 0.00529, -0.00812, 0.016, 0.00254, -0.00499, -0.07594, 0.04032, 0.03074, 0.01812],
        "Sviluppo": [0.02787, 0.02466, -0.01916, 0.07421, 0.03317, 0.05396, -0.10544, 0.06917, 0.05155, 0.04393],
        "Dinamico": [0.17927, 0.05428, -0.01314, 0.10553, 0.10981, 0.11292, 0.05357, 0.03924, 0.06711, -0.0311, 0.12792, 0.05032, 0.1154, -0.11458, 0.10192, 0.08627, 0.07318],
        "Crescita": [0.12131, 0.03909, -0.00205, 0.08736, 0.07985, 0.0938, 0.0345, 0.0396, 0.03596, -0.0113, 0.10538, 0.05295, 0.06857, -0.12082, 0.07888, 0.05727, 0.04688],
    },
}

# ---------------------------------------------------------------------------
# STORICO RENDIMENTI MENSILI per comparto (per il block-bootstrap mensile)
# ---------------------------------------------------------------------------
# Rendimenti mensili semplici (ordine cronologico crescente) calcolati dalle
# quote ufficiali Cometa. Stessa fonte dello storico annuale: le due tabelle
# sono coerenti per costruzione (l'annuale e' il composto dei 12 mesi).
STORICO_MENSILE = {
    "Cometa": {
        "Garantito": [0.0073, 0.008141, 0.004136, 0.003432, 0.000293, 0.020518, 0.004978, -0.003334, -0.004588, 0.011619, -0.001424, 0.003327, 0.006063, 0.009323, 0.000467, -0.009326, -0.003577, 0.005574, 0.001785, -0.012567, -0.02004, -0.01289, -0.022288, -0.008636, -0.020259, 0.029053, -0.030242, -0.030667, 0.006947, 0.016453, -0.023392, 0.018606, -0.013332, 0.013831, 0.001784, 0.00199, -0.001986, 0.003143, 0.001044, -0.012101, 0.002746, 0.020114, 0.022401, -0.000303, -0.006262, 0.008233, -0.007964, 0.001931, 0.003245, 0.01486, 0.00259, 0.010432, -0.006391, 0.013953, -0.006344, 0.003438, 0.004992, -0.00711, 0.00981, 0.004371, 0.000484, 0.000773, 0.001932, 0.002603, 0.005962, 0.000669, -0.002102, 0.006318, 0.00761, -0.020959, 0.006557, 0.008527],
        "Bilanciato": [0.003679, 0.004727, 0.007296, 0.002573, 0.005039, 0.004635, 0.001506, 0.001504, 0.001126, 0.002532, 0.002058, 0.00168, -0.000186, 0.025815, 0.00536, -0.000452, -0.008227, 0.000273, 0.004466, 0.011976, -0.008517, 0.00859, -0.012103, 0.011979, 0.00556, -0.015964, -0.003444, 0.010095, 0.004682, -0.003136, -0.001259, -0.008101, -0.00608, 0.012417, 0.004599, 0.003321, -0.004742, -0.00027, 0.004046, -0.003941, -0.005664, -0.010308, -0.008314, 0.004054, -0.011103, 0.01132, 0.007707, -0.005463, -0.007507, 0.000277, -0.00332, 0.013509, 0.006756, 0.006801, 0.001081, 0.005668, -0.000447, 0.006534, 0.000267, 0.010312, 0.007919, 0.007595, 0.001473, -0.000519, -0.001298, 0.004507, -0.000863, 0.00285, 0.001981, 0.004297, 0.006161, 0.004337, 0.004488, 0.00489, 0.001342, 0.00243, 0.012286, 0.011724, 0.003427, 0.005205, 0.006958, -0.012052, 0.012362, 0.011889, 0.00262, 0.004909, -0.004807, -0.004751, -0.010342, 0.000482, 0.00699, 0.012687, 0.008352, 0.008673, 0.003408, 0.000618, 0.002855, 0.002231, 0.001535, 0.007665, 0.002434, -0.004856, 0.002059, 0.00525, 0.001892, 0.008462, -0.002547, -0.001052, -0.007368, -0.000454, -0.010079, 0.007043, -0.002737, -0.019285, 0.006296, 0.01398, -0.018129, -0.019395, 0.00712, 0.00762, -0.009355, -0.010939, 0.008991, 0.018059, 0.001936, 0.006417, 0.022123, 0.014505, 0.010667, -0.006304, 0.011581, 0.00299, -0.002254, 0.004882, 0.015445, 0.002642, -0.003276, -0.0005, 0.012582, 0.007766, 0.002802, 0.002515, -0.015401, 0.005591, 0.002041, 0.005408, -0.004401, 0.008841, 0.005773, -0.003873, -0.002013, -0.002226, -0.001046, 0.001256, -0.014638, 0.021788, 0.0135, 0.012364, -0.000202, -0.00081, -0.000203, 0.00277, 0.014552, 0.008433, 0.007178, 0.003596, 0.009446, 0.005163, 0.003146, 0.002048, 0.005685, 0.016577, -0.003936, -0.01819, 0.014183, -0.005165, 0.009625, 0.015992, 0.00358, -0.000984, 0.008681, 0.011109, 0.006761, 0.006656, 0.010365, 0.006367, 0.002636, 0.01303, -0.000461, 0.001039, 0.011702, 0.002393, 0.017393, 0.010894, 0.007682, -0.006472, -0.004527, -0.017801, 0.016317, -0.016499, 0.002146, 0.016007, 0.005825, -0.011141, -0.000223, 0.001227, 0.009194, -0.001767, 0.00708, 0.007854, 0.009155, -0.000702, 0.000378, -0.010425, -0.008242, 0.011888, -0.008268, 0.005978, 0.001308, 0.004683, 0.003794, -0.003509, 0.00428, 0.003075, 0.002904, 0.008741, 0.001116, 0.000266, 0.003398, -0.010317, -0.002994, 0.003325, -0.004115, -0.000429, 0.006013, -0.001708, 0.000428, -0.01539, 0.001248, -0.009648, 0.015489, 0.005551, 0.009809, 0.005679, -0.006439, 0.015511, 0.006434, 0.006237, 0.002014, -0.000309, 0.003403, 0.003392, 0.007836, -0.015245, -0.04985, 0.017652, 0.008059, 0.00773, 0.010665, 0.005562, -0.003205, -0.004253, 0.024531, 0.007625, -0.001968, -0.002679, 0.008262, 0.007792, 0.003442, 0.007258, 0.007156, 0.004802, -0.010095, 0.00739, -0.002983, 0.008976, -0.018279, -0.014608, -0.002613, -0.023681, -0.004541, -0.024885, 0.024191, -0.019466, -0.0297, 0.006984, 0.01826, -0.01905, 0.021264, -0.013757, 0.013195, 0.002073, -0.001326, 0.004993, 0.005655, -0.003521, -0.015295, -0.007338, 0.029513, 0.024632, 0.003018, 0.002397, 0.013888, -0.013598, 0.009817, 0.009722, 0.01332, 0.004628, 0.009801, -0.008007, 0.019764, -0.010266, 0.010421, 0.002255, -0.019145, 0.00039, 0.01317, 0.008088, 0.006543, 0.004318, 0.011197, 0.013082, 0.000876, -0.000783, 0.009822, 0.012603, -0.030259, 0.024182, 0.019116],
        "Azionario": [0.017384, 0.019141, 0.012736, 0.000637, 0.015113, -0.019041, 0.023964, 0.016616, 0.00706, 0.00861, 0.001133, -0.00332, -0.024606, 0.000466, 0.007371, 0.01679, 0.010453, 0.013268, 0.000888, 0.009683, 0.008858, -0.001234, 0.002252, 0.013048, 0.008587, -0.002696, -0.011596, 0.001008, 0.004745, 0.00551, -0.016155, -0.003111, -0.03367, -0.001652, -0.018353, 0.023293, 0.002845, -0.0448, -0.000469, 0.017127, -0.04521, -0.062248, 0, -0.002061, -0.014026, -0.028626, 0.016981, 0.048414, 0.014157, 0.004155, 0.036988, 0.016598, 0.019231, -0.012091, 0.013564, 0.016382, -0.014453, 0.008292, 0.033354, -0.002432, -0.020906, -0.012751, 0.013068, 0.006412, 0.014692, 0.007461, -0.009019, 0.01835, 0.00574, 0.010837, -0.008148, 0.013907, 0.003127, -0.008431, -0.005644, -0.022562, -0.007792, 0.016893, -0.011075, 0.011493, 0.0236, 0.020138, 0.002651, -0.002505, -0.018064, 0.016123, 0.013351, 0.014693, 0.009721, 0.005992, 0.011846, 0.011839, 0.016015, 0.000515, 0.00508, 0.021945, 0.006135, -0.025512, 0.024328, -0.006857, 0.017386, 0.023197, 0.007537, 0.003531, -0.002624, 0.018954, 0.002288, 0.005972, 0.012454, 0.005748, -0.002057, 0.015177, -0.00457, -0.002097, 0.018912, -0.000669, 0.019131, 0.01921, 0.006444, -0.002721, 0.001979, -0.023333, 0.020446, -0.027858, -0.00766, 0.027823, 0.005727, -0.015257, -0.014839, -0.00371, 0.015508, 0.002408, 0.008354, -0.006227, 0.018145, 0.004549, -0.000799, -0.006025, -0.000644, 0.020451, -0.003524, 0.012669, 0.004327, 0.00545, 0.007485, -0.004253, 0.004785, 0.002765, 0.006026, 0.010356, 0.0001, 0.001356, 0.009332, -0.019435, -0.005931, 0.008516, -0.002376, -0.000608, 0.012273, -0.002054, 0.001255, -0.027978, 0.002167, -0.022287, 0.025007, 0.013816, 0.012463, 0.011208, -0.010837, 0.021211, 0.006613, 0.006813, 0.004833, 0.002934, 0.006475, 0.007339, 0.005724, -0.028128, -0.066112, 0.030784, 0.009201, 0.006626, 0.013709, 0.007323, -0.006543, -0.007659, 0.032988, 0.010232, -0.003816, -0.00506, 0.01136, 0.012548, 0.004317, 0.01123, 0.008638, 0.006887, -0.01629, 0.011299, -0.00389, 0.014077, -0.022704, -0.018283, -0.000793, -0.030643, -0.002409, -0.032509, 0.030306, -0.023551, -0.039404, 0.011883, 0.031706, -0.030732, 0.033749, -0.014372, 0.015133, 0.004591, 0.002506, 0.019361, 0.012021, -0.009122, -0.020235, -0.014731, 0.046891, 0.028468, 0.007843, 0.016845, 0.020708, -0.018656, 0.01892, 0.017908, 0.009273, 0.007771, 0.011162, -0.008174, 0.028503, -0.011441, 0.017004, -0.00189, -0.03268, -0.007404, 0.025634, 0.014252, 0.014423, 0.004672, 0.018478, 0.018302, -0.000312, 0.001716, 0.011485, 0.012124, -0.036469, 0.044441, 0.028001],
        "Monetario": [0.001421, 0.002587, 0.001998, 0.003822, 0.001655, 0.000496, 0.002312, 0.001483, 0.002633, 0.0032, 0.001309, 0.000899, 0.003101, 0.00122, 0.002275, 0.003973, 0.002342, 0.002014, 0.003377, 0.001843, 0.003279, 0.003109, 0.002702, 0.003091, 0.00324, 0.002678, -0.000393, -0.002593, 0.002285, 0.003931, -0.000392, 0.002193, 0.003517, -0.000312, -0.001325, 0.004291, 0.002564, -0.001395, 0.004268, 0.003631, 0.000385, -0.000308, 0.004157, 0.003986, 0.004887, 0.001596, 0.003565, 0.003024, 0.002487, 0.001955, 0.002776, 0.001048, 0.001794, 0.000373, 0.000671, 0.000745, 0.000596, 0.002084, 0.000743, -0.000371, 0.000223, 0.000148, 0.001781, 0.001111, -0.000962, 0.001259, -0.006659, 0.003948, 0.004006, 0.001773, 0.00177, 0.000515, 0.001987, 0.000514, -0.004184, 0.005455, -0.000367, -0.001174, -0.004479, 0.011802, 0.006999, 0.00695, -0.000935, -0.000648, -0.004249, 0.003833, 0.003746, 0.005742, 0.002212, 0.001923, 0.002558, 0.001134, 0.001629, 0, 0.001131, 0.003248, 0, -0.002111, 0.00268, 0.000563, 0.001195, 0.00323, 0.0014, -0.000419, 0.002517, 0.001325, 0.000557, 0.000348, 0.001183, 0.001877, 0.000902, 0.00104, 0.000277, -0.001315, 0.001317, 0.000208, 0.001453, 0.001313, 0.00069, 0, 0.000414, -0.001724, 0.001796, -0.000138, 0.000138, 0.000483, 0.000551, -0.000275, 0.000138, 0, 0, 0.000276, 0.000482, 0.000275, -0.000344, 0.000275, -6.9e-05, -0.001239, -0.001171, 0.003104, -0.001513, -0.000413, -0.000965, 0.000483, 0.000207, -0.000689, 0.000828, 0.000207, -0.000344, 0.000551, -0.000413, -0.000827, -0.001104, -6.9e-05, -0.000138, -0.000276, -0.005872, 0.00132, 0.000347, -0.002012, 0.000834, 6.9e-05, 0.000139, 0.00125, 0.001318, 0, 0.001593, 0.000138, -0.000138, 0.001176, 0.00076, 0.001104, -0.000689, -0.00069, -0.000552, -6.9e-05, 0.001174, -0.000345, -0.007178, 0.002086, 0.002081, 0.0027, 0.001726, 0.000551, 0.000689, 0.001033, 0.000756, -0.000137, -0.000275, -0.0011, 0.000688, -0.000344, -6.9e-05, 6.9e-05, 0.000757, -0.000412, -0.000619, -0.00172, 0.000207, -0.000276, -0.001792, -0.004075, -0.003121, -0.003478, -0.001536, -0.004405, 0.004284, -0.006363, -0.007178, 0.000284, 0.00163, -0.003608, 0.003692, -0.003962, 0.006179, 0.001412, 0.000987, -0.00169, 0.003456, 0.002882, 0.000701, 0.003292, 0.005236, 0.006528, 0.001794, -0.000964, 0.003378, 6.9e-05, 0.002611, 0.003426, 0.005805, 0.003327, 0.005143, -0.000135, 0.00505, 0.001072, 0.002409, 0.003071, 0.000932, 0.003923, 0.001325, 0.001521, 0.001387, 0.001781, 0.001317, 0.00263, 0.001049, 0.000786, 0.002422, 0.002612, -0.006253, 0.002622, 0.003007],
    },
    "Fon.Te": {
        "Conservativo": [0.006033, -0.004474, -0.00306, -0.007577, -0.003769, 0.005918, 0.006847, 0.007854, 0.012355, 0.009294, 0.001023, 0.004274, 0.006292, 0.005793, 0.002834, 0.001003, 0.000455, 0.005553, 0.003711, 0.003157, -0.001528, 0.002071, 0.004493, 0.000537, 0.003755, 0.004899, 0.000443, -0.001861, -0.001598, 0.000622, 0.00462, -0.002388, 0.000355, -0.00514, 0.006414, 0.001682, 0.002386, -0.001587, 0.002119, 0.002115, -0.000615, -0.005806, 0.004778, -0.004491, 0.002477, -0.014208, 0.021305, 0.012446, 0.009869, 0.000943, -0.001285, -0.003259, 0.003269, 0.007804, 0.007658, 0.005236, 0.003444, 0.007451, 0.002493, -0.000249, 0.000663, 0.002651, 0.010578, -0.00139, -0.008271, 0.007266, -0.000328, 0.00369, 0.00817, 0.004781, -0.001613, 0.005574, 0.00482, 0.003598, 0.00239, 0.00453, 0.005063, 0.00244, 0.004005, 0.002425, -0.001873, 0.003518, 0.001324, 0.004356, 0.006816, 0.002077, -0.001228, -0.000307, -0.007996, 0.008448, -0.006072, 0.002861, 0.009099, 0.004203, -0.004261, 0.001987, 0.000305, 0.00305, -0.001444, 0.002969, 0.001063, 0.002426, 0.001134, -0.000302, -0.004912, -0.003265, 0.007619, -0.005142, 0.002128, 0.000607, 0.001668, 0.00174, -0.000302, 0.001587, 0.000453, 0.00098, 0.00339, 0.000901, -0.0027, 0.000451, -0.000677, 0.001881, 0.001427, -0.017996, 0.005727, 0, -0.00782, 0.00352, -0.001373, 0.00504, 0.001899, 0.004626, -7.5e-05, 0.003095, 0.001731, -0.002629, 0.004896, 0.003373, 0.001195, 0.000448, -0.000746, -7.5e-05, 7.5e-05, 0.003284, -0.00372, -0.007766, 0.001355, 0.001278, 0.001801, 0.001124, -0.00015, 0.001422, 0.000598, 0.002614, 0.000745, -0.002308, -0.005, 0.002925, -0.001795, -7.5e-05, 0.002547, 0.005679, -0.001115, -0.004017, -0.003212, 0.003896, -0.002463, -0.006659, -0.008436, -0.006305, -0.012537, -0.006813, -0.008652, 0.01376, -0.023268, -0.01882, 0.004451, 0.007977, -0.01279, 0.009393, -0.007621, 0.009053, 0.001522, 0.00272, -0.002234, 0.004557, 0.00183, -0.006594, 0.003279, 0.011478, 0.012451, 0.001245, -0.002799, 0.005613, -0.003333, 0.002178, 0.004346, 0.008114, 0.00253, 0.006958, -0.001974, 0.009814, -0.00226, 0.003096, 0.001506, -0.004134, 0.004227, 0.003758, 0.001348, 0.001346, 0, 0.00224, 0.006855, 0.00037, -0.002589, 0.006304, 0.005896, -0.013115, 0.008687, 0.007066],
        "Sviluppo": [0.000341, -0.016694, 0.015072, -0.019741, -0.002263, 0.019544, 0.007417, -0.012346, -0.008028, -0.002197, 0.008284, 0.001149, 0.007174, 0.003305, 0.01062, 0.002416, 0.000112, -0.007175, -0.000395, 0.012482, -0.0053, 0.01116, 0.002385, 0.002988, 0.001655, -0.00336, 0.001382, 0.001435, 0.004739, 0.009379, -0.001304, -0.000653, 0.001905, -0.005597, -0.00306, 0.005481, -0.003543, -0.000328, 0.006239, -0.00174, 0.002016, -0.013267, 0.003141, -0.010382, 0.014321, 0.005308, 0.010887, 0.005708, -0.005943, 0.015297, 0.008541, 0.005944, 0.004392, -0.001614, 0.00803, 0.001138, 0.009973, -0.012688, -0.046637, 0.02647, 0.009425, 0.013009, 0.005178, 0.006749, -0.001023, -0.008503, 0.02764, 0.005228, -0.0018, -0.003257, 0.015482, 0.001634, 0.005881, 0.009187, 0.008763, 0.006756, -0.010402, 0.009397, 0.000528, 0.010792, -0.017367, -0.018495, -0.00615, -0.018911, -0.006156, -0.022847, 0.029201, -0.025192, -0.033042, 0.011837, 0.021596, -0.023212, 0.020953, -0.011223, 0.013347, 0.003733, 0.002583, 0.003195, 0.006164, -0.002808, -0.010853, -0.006625, 0.026988, 0.022524, 0.007144, -0.000837, 0.013114, -0.011923, 0.007732, 0.011143, 0.010005, 0.003972, 0.007102, -0.007147, 0.017352, -0.006841, 0.011748, 0.006016, -0.013721, 0.000846, 0.011881, 0.004316, 0.003882, 0.002762, 0.007207, 0.008249, 0.001266, -0.001129, 0.002576, 0.014696, -0.025057, 0.013397, 0.014434],
        "Dinamico": [0, 0, 0.0032, -0.008373, -0.053981, -0.026458, -0.024667, -0.014212, -0.027585, 0.022648, 0.05274, 0.01388, -0.002139, 0.054662, 0.016362, 0.014799, -0.01074, 0.014044, 0.035065, -0.013285, 0.015195, 0.038367, -0.003741, -0.016026, -0.006608, 0.013584, -0.001294, 0.002869, 0.005999, 0.002936, 0.01619, 0.00405, 0.010937, -0.022612, 0.008619, 0.003958, -0.009049, -0.011121, -0.037579, -0.015105, 0.032603, -0.002055, 0.026303, 0.026268, 0.017241, 0.00463, -0.005479, -0.019675, 0.015699, 0.026082, 0.002996, 0.008362, -0.000338, 0.013883, 0.012023, 0.01386, 0.011962, 0.016806, 0.019296, 0.001319, -0.025957, 0.02283, -0.011277, 0.021474, 0.026105, 0.009231, 0.000297, -0.011151, 0.020223, 0.000442, 0.002431, 0.021014, 0.002447, -0.002872, 0.02347, 0.008652, 0.008299, 0.021926, 0.013266, 0.025984, 0.039193, 0.017667, -0.009973, 0.01113, -0.022938, 0.0107, -0.033815, -0.017467, 0.041328, 0.016442, -0.022436, -0.031129, -0.011386, 0.013238, 0.006141, 0.011427, 0.002953, 0.025602, 0.002434, 0.000498, -0.0084, 0.00753, 0.020927, -0.002135, 0.022804, 0.005619, 0.005171, 0.002129, -0.004367, 0.001541, 0.00213, 0.012814, 0.016616, 0.000975, 0.002177, 0.014464, -0.01685, -0.012954, 0.01446, 0.002118, -0.002056, 0.018661, 0.000337, 0.004662, -0.02941, 0.008814, -0.032206, 0.028204, 0.015437, 0.016445, 0.014789, -0.018573, 0.029699, 0.013337, 0.000482, 0.01385, -0.008017, 0.010741, 0.005629, 0.007219, -0.029968, -0.061145, 0.04876, 0.011637, 0.015588, 0.004287, 0.017233, -0.005129, -0.017549, 0.05274, 0.010926, 5e-05, 0.001893, 0.03256, 0.005392, 0.007518, 0.013117, 0.010555, 0.012487, -0.018798, 0.026915, -0.003322, 0.022416, -0.023889, -0.019213, 0.007416, -0.02676, -0.010513, -0.031731, 0.037885, -0.031144, -0.041033, 0.026878, 0.031089, -0.035695, 0.02693, -0.013259, 0.019012, 0.004835, 0.006464, 0.012701, 0.010348, -0.007552, -0.014648, -0.010667, 0.037955, 0.026979, 0.014325, 0.008167, 0.020453, -0.01592, 0.010206, 0.021397, 0.006004, 0.004379, 0.00684, -0.006623, 0.023422, -0.00877, 0.022751, 0.002842, -0.025099, -0.004466, 0.026453, 0.007999, 0.008918, 0.001662, 0.015179, 0.014234, -0.001848, 0.00323, 0.003376, 0.021676, -0.041743, 0.028655, 0.025992],
        "Crescita": [0, 0.019, 0.002944, -0.002838, -0.03297, -0.01106, -0.012108, -0.009659, -0.022653, 0.014487, 0.035752, 0.006944, 0.00071, 0.039526, 0.014039, 0.011441, -0.007129, 0.01034, 0.023027, -0.007503, 0.011946, 0.027575, -0.00377, -0.00964, -0.00473, 0.009597, 0.002082, 0.000542, 0.003431, -0.00198, 0.011451, 0.002229, 0.006938, -0.01484, 0.006097, 0.004189, -0.006479, -0.008933, -0.019558, -0.010204, 0.019318, -0.006014, 0.026217, 0.021259, 0.015132, 0.002671, -0.004211, -0.013548, 0.009973, 0.020875, 0.003733, 0.007101, 0.000588, 0.011744, 0.009286, 0.008872, 0.008631, 0.01219, 0.017307, -0.000549, -0.020082, 0.016891, -0.00803, 0.015475, 0.020397, 0.007276, -0.000532, -0.004488, 0.014978, 0.002183, 0.002254, 0.017015, 0.002874, -0.001102, 0.01854, 0.003756, 0.006045, 0.017167, 0.011111, 0.021769, 0.024709, 0.013086, -0.009704, 0.002913, -0.019608, 0.010707, -0.021121, -0.009529, 0.027281, 0.011773, -0.016595, -0.013177, -0.007358, 0.010226, 0.001291, 0.010992, 0.00906, 0.018025, 0.001829, -0.000261, -0.008545, 0.002632, 0.014699, -0.00582, 0.018864, 0.002171, 0.003122, 0.000826, -0.00533, -0.000191, 0.002935, 0.006044, 0.011067, 0.000876, 0.001062, 0.005993, -0.007881, -0.005567, 0.009057, 0.003054, -0.000311, 0.009697, 0.0008, 0.001538, -0.015601, 0.006177, -0.017859, 0.018879, 0.0088, 0.015541, 0.008045, -0.006961, 0.01982, 0.013035, 0.008247, 0.008354, -0.0042, 0.009128, 0.00229, 0.016279, -0.019278, -0.047109, 0.037349, 0.009334, 0.013556, 0.006744, 0.009457, -0.001673, -0.012345, 0.034557, 0.007763, -0.001356, -0.007116, 0.021064, 0.004983, 0.006131, 0.010916, 0.011323, 0.008086, -0.01743, 0.018367, 0.000103, 0.012074, -0.019241, -0.016305, -0.002, -0.022567, -0.011544, -0.025213, 0.035998, -0.031937, -0.038629, 0.015794, 0.024294, -0.03354, 0.022809, -0.013606, 0.017571, 0.003319, 0.003924, 0.005082, 0.005611, -0.004641, -0.012655, -0.007421, 0.030811, 0.026593, 0.007011, -0.000159, 0.014884, -0.014875, 0.007603, 0.015778, 0.009558, 0.003293, 0.008975, -0.007828, 0.021005, -0.008781, 0.015541, 0.003041, -0.022662, -0.001475, 0.018129, 0.004802, 0.006421, -0.000346, 0.011776, 0.012128, -0.000531, -0.00029, 0.003675, 0.019223, -0.032616, 0.019448, 0.018262],
    },
}

def annuale_disponibile(fondo: str, comparto: str, min_anni: int = 5) -> bool:
    serie = STORICO_ANNUALE.get(fondo, {}).get(comparto, [])
    return len(serie) >= min_anni

def mensile_disponibile(fondo: str, comparto: str, min_mesi: int = 24) -> bool:
    serie = STORICO_MENSILE.get(fondo, {}).get(comparto, [])
    return len(serie) >= min_mesi

# ---------------------------------------------------------------------------
# COEFFICIENTI DI CRESCITA per tipo lavoratore (solo Operaio / Impiegato)
# ---------------------------------------------------------------------------
COEFF_LAVORATORE = {
    "Operaio":   0.88,
    "Impiegato": 1.08,
}

# ---------------------------------------------------------------------------
# CATALOGO ETF PREDEFINITI — ticker Yahoo Finance (SOLO accumulazione UCITS)
# ---------------------------------------------------------------------------
# Catalogo curato per contenere solo ETF/ETC UCITS ad ACCUMULAZIONE (i proventi
# vengono reinvestiti, coerente con un PAC di lungo periodo). I ticker noti come
# "a distribuzione" sono stati rimossi dal catalogo e finiscono nella lista
# ETF_FLAG piu' sotto, che alimenta il controllo automatico.
CATALOGO_ETF = {
    "Azionario Globale": {
        "iShares Core MSCI World Acc (SWDA.MI)": "SWDA.MI",
        "Vanguard FTSE All-World Acc (VWCE.DE)": "VWCE.DE",
        "Xtrackers MSCI World Acc (XDWD.MI)": "XDWD.MI",
        "iShares MSCI ACWI Acc (SSAC.MI)": "SSAC.MI",
    },
    "Azionario USA": {
        "iShares Core S&P 500 Acc (CSSPX.MI)": "CSSPX.MI",
        "Xtrackers S&P 500 Acc (XSPX.MI)": "XSPX.MI",
        "Invesco Nasdaq-100 Acc (EQAC.MI)": "EQAC.MI",
    },
    "Azionario Europa": {
        "Xtrackers Euro Stoxx 50 Acc (XESC.MI)": "XESC.MI",
        "iShares Core MSCI EMU Acc (CEBL.MI)": "CEBL.MI",
    },
    "Azionario Mercati Emergenti": {
        "iShares Core MSCI EM IMI Acc (EIMI.MI)": "EIMI.MI",
        "Xtrackers MSCI Emerging Markets Acc (XMME.MI)": "XMME.MI",
    },
    "Obbligazionario": {
        "iShares Core Global Aggregate Bond EUR-H Acc (AGGH.MI)": "AGGH.MI",
        "Xtrackers Global Government Bond EUR-H Acc (XG7S.MI)": "XG7S.MI",
    },
    "Oro e Materie Prime": {
        "iShares Physical Gold ETC (SGLN.MI)": "SGLN.MI",
        "Invesco Physical Gold ETC (SGLD.MI)": "SGLD.MI",
        "WisdomTree Broad Commodities Acc (WCOA.MI)": "WCOA.MI",
    },
    "Immobiliare (REIT)": {
        "Xtrackers FTSE EPRA/NAREIT Global Acc (XREA.MI)": "XREA.MI",
    },
}
# Mappa inversa ticker -> nome leggibile, utile per la legenda finale
TICKER_TO_NOME = {t: nome for cat in CATALOGO_ETF.values() for nome, t in cat.items()}
# Insieme dei ticker "certificati" ad accumulazione UCITS dal catalogo
WHITELIST_ACC_UCITS = set(TICKER_TO_NOME.keys())

# Ticker noti come NON ad accumulazione (a distribuzione) o da verificare.
# Usati per avvisare l'utente se li inserisce a mano.
ETF_FLAG = {
    "EQQQ.MI": "a DISTRIBUZIONE — la versione ad accumulo è EQAC.MI (o SB.. classi acc)",
    "EXSA.MI": "a DISTRIBUZIONE (iShares STOXX Europe 600, dist)",
    "IWDP.MI": "a DISTRIBUZIONE (Property *Yield*)",
    "IBGX.MI": "a DISTRIBUZIONE (iShares Euro Gov Bond 3-5y, dist)",
    "IEBC.MI": "a DISTRIBUZIONE (iShares Euro Corporate Bond, dist)",
    "EMU.MI":  "DA VERIFICARE (esistono classi dist e acc con ticker vicini)",
    "IWRD.MI": "a DISTRIBUZIONE (versione acc: SWDA.MI)",
    "VWRL.MI": "a DISTRIBUZIONE (versione acc: VWCE.DE)",
}

def classifica_ticker(ticker: str):
    """
    Ritorna (stato, nota) sullo stato di accumulazione/UCITS di un ticker.
    stato ∈ {"ok", "warn", "sconosciuto"}.
    - "ok": presente nel catalogo curato (accumulazione UCITS).
    - "warn": presente in ETF_FLAG (distribuente o da verificare).
    - "sconosciuto": non classificabile automaticamente -> l'utente deve
      verificarne dist/acc e status UCITS sulla scheda (KID/factsheet).
    Nota: Yahoo Finance NON espone in modo affidabile il flag dist/acc, quindi
    la verifica automatica si basa su una whitelist curata, non sui dati Yahoo.
    """
    t = ticker.strip().upper()
    if t in WHITELIST_ACC_UCITS:
        return "ok", "accumulazione UCITS (da catalogo curato)"
    if t in ETF_FLAG:
        return "warn", ETF_FLAG[t]
    return "sconosciuto", ("non in whitelist: può essere un ETF non catalogato "
                           "o un'AZIONE SINGOLA. Le azioni singole sono ammesse "
                           "ma hanno volatilità molto più alta di un ETF "
                           "diversificato e possono compromettere l'analisi "
                           "(la stima storica di rendimento/rischio su un solo "
                           "titolo è poco affidabile). Se è un ETF, verifica "
                           "sul KID che sia ad accumulazione e UCITS.")

# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------
st.sidebar.header("1. Contratto e Inquadramento")
ccnl_scelto = st.sidebar.selectbox("CCNL / Fondo negoziale", list(CCNL_PRESET.keys()), index=0)
preset = CCNL_PRESET[ccnl_scelto]
mensilita = preset["mensilita"]

livello = st.sidebar.selectbox("Livello di inquadramento", list(preset["livelli"].keys()))
minimo_mensile = preset["livelli"][livello]
minimo_annuo = minimo_mensile * mensilita

scatto_valore_livello = preset.get("scatti_valore_livello", {}).get(
    livello, preset["scatto_valore"]
)
comparti_base = list(preset["comparti"].keys())

st.sidebar.caption(
    f"Minimo tabellare **{livello}**: {minimo_mensile:,.0f} €/mese × {mensilita} "
    f"mensilità = **{minimo_annuo:,.0f} €/anno**"
)

st.sidebar.markdown("**Composizione della RAL**")
anni_anzianita_pregressi = st.sidebar.number_input(
    "Scatti di anzianità già maturati", min_value=0, max_value=preset["scatti_max"],
    value=0, step=1,
    help=f"Max {preset['scatti_max']} scatti, uno ogni {preset['scatto_ogni_anni']} anni. "
         f"Livello {livello}: {scatto_valore_livello:.1f} €/mese ciascuno",
)
superminimo_mensile = st.sidebar.number_input(
    "Superminimo (€/mese)", min_value=0, value=0, step=50,
    help="Voce individuale non prevista dal contratto. NON entra nella base "
         "di calcolo del contributo aziendale al fondo.",
)
premio_produzione_annuo = st.sidebar.number_input(
    "Premio di produzione (€/anno)", min_value=0, value=0, step=200,
    help="Premio di risultato variabile. NON entra nella base del contributo "
         "aziendale al fondo.",
)

st.sidebar.markdown("**Override manuale (opzionale)**")
ral_manuale = st.sidebar.number_input(
    "RAL effettiva a mano (€/anno, 0 = auto)", min_value=0, value=0, step=1000,
    help="Se la conosci, inserisci la tua RAL reale. Sostituisce quella calcolata "
         "e viene usata per TFR e IRPEF. Il contributo AZIENDA resta comunque "
         "calcolato sui minimi tabellari + scatti (come da contratto).",
)
capitale_iniziale_fondo = st.sidebar.number_input(
    "Capitale già presente nel fondo (€)", min_value=0, value=0, step=1000,
    help="Montante già accumulato se sei iscritto da tempo.",
)
capitale_iniziale_pac = st.sidebar.number_input(
    "Capitale già presente nel PAC (€)", min_value=0, value=0, step=1000,
    help="Montante ETF già accumulato, se il PAC è già avviato da tempo.",
)

st.sidebar.header("2. Profilo Lavoratore")
eta = st.sidebar.number_input("Età attuale", min_value=18, max_value=67, value=30, step=1)
tipo_lavoratore = st.sidebar.selectbox("Tipo di lavoratore", list(COEFF_LAVORATORE.keys()), index=1)
profilo_crescita = st.sidebar.selectbox(
    "Dinamismo di carriera",
    ["Moderata (2–5%/scatto)", "Media (3–7%/scatto)", "Spinta (6–10%/scatto)"],
    index=1,
)
crescita_base = st.sidebar.slider(
    "Crescita di base annua (inflazione + rinnovi CCNL) %", 0.0, 4.0, 2.0, 0.1,
    help="Adeguamento applicato ogni anno anche senza promozioni (~1,5–2,5% storico).",
) / 100

# --- Orizzonte spostato in alto: serve alle sezioni carriera/CCNL/disoccup. ---
durata = st.sidebar.slider("Anni di investimento", 1, 40, 25)

st.sidebar.markdown("**Passaggi di livello (promozioni pianificate)**")
usa_passaggi_livello = st.sidebar.checkbox(
    "Pianifica cambi di livello/mansione durante la carriera", value=False,
    help="Indica TU in quali anni futuri passerai a un livello superiore. Il "
         "nuovo minimo tabellare sostituisce la base da quell'anno; sopra continua "
         "la crescita simulata (scatti stocastici + inflazione).",
)
livelli_ccnl_lista = list(preset["livelli"].keys())
passaggi_livello = []  # lista di (anno_da, livello)
if usa_passaggi_livello:
    n_passaggi = st.sidebar.number_input(
        "Numero di passaggi di livello pianificati", min_value=1, max_value=10,
        value=1, step=1, key="n_passaggi_livello",
    )
    for i in range(int(n_passaggi)):
        pc1, pc2 = st.sidebar.columns([1, 2])
        anno_da = pc1.number_input(
            f"Anno #{i+1}", min_value=1, max_value=40, value=min(5 * (i + 1), 40),
            step=1, key=f"anno_passaggio_{i}",
        )
        livello_nuovo = pc2.selectbox(
            f"Nuovo livello #{i+1}", livelli_ccnl_lista,
            index=min(i + 1, len(livelli_ccnl_lista) - 1),
            key=f"livello_passaggio_{i}",
        )
        passaggi_livello.append((int(anno_da), livello_nuovo))
    passaggi_livello.sort(key=lambda x: x[0])

# --- NUOVO: Cambio CCNL / fondo durante la carriera --------------------------
st.sidebar.markdown("**Cambio CCNL / fondo (cambio settore)**")
usa_cambio_ccnl = st.sidebar.checkbox(
    "Pianifica uno o più cambi di CCNL durante la carriera", value=False,
    help="Simula un cambio di settore/contratto: da un certo anno cambiano "
         "contributi, TFR, costi, comparto e minimi tabellari (nuovo fondo).",
)
cambi_ccnl = []  # lista di (anno_da, ccnl_name, livello, comparto)
if usa_cambio_ccnl:
    n_cambi = st.sidebar.number_input(
        "Numero di cambi CCNL pianificati", min_value=1, max_value=6,
        value=1, step=1, key="n_cambi_ccnl",
    )
    for i in range(int(n_cambi)):
        anno_c = st.sidebar.number_input(
            f"Cambio #{i+1} — anno", min_value=1, max_value=40,
            value=min(10 * (i + 1), 40), step=1, key=f"anno_ccnl_{i}",
        )
        ccnl_new = st.sidebar.selectbox(
            f"Cambio #{i+1} — nuovo CCNL", list(CCNL_PRESET.keys()),
            key=f"ccnl_new_{i}",
        )
        preset_new = CCNL_PRESET[ccnl_new]
        liv_new = st.sidebar.selectbox(
            f"Cambio #{i+1} — livello", list(preset_new["livelli"].keys()),
            key=f"liv_ccnl_{i}",
        )
        _cn = list(preset_new["comparti"].keys())
        comp_new = st.sidebar.selectbox(
            f"Cambio #{i+1} — comparto", _cn,
            index=_cn.index("Azionario") if "Azionario" in _cn else len(_cn) - 1,
            key=f"comp_ccnl_{i}",
        )
        cambi_ccnl.append((int(anno_c), ccnl_new, liv_new, comp_new))
    cambi_ccnl.sort(key=lambda x: x[0])

# --- NUOVO: Periodi di disoccupazione ----------------------------------------
st.sidebar.markdown("**Periodi di disoccupazione**")
usa_disoccupazione = st.sidebar.checkbox(
    "Inserisci periodi senza reddito", value=False,
    help="Negli anni indicati: nessun contributo (TFR, azienda, tuo, PAC) e "
         "RAL a zero. I capitali già accumulati continuano comunque a rendere.",
)
anni_disoccupato = set()
if usa_disoccupazione:
    anni_disoccupato = set(st.sidebar.multiselect(
        "Anni di disoccupazione", list(range(1, durata + 1)),
        help="Anno 1 = primo anno di simulazione.",
    ))

st.sidebar.header("3. Fondo")
_idx_comp = comparti_base.index("Azionario") if "Azionario" in comparti_base else len(comparti_base) - 1
comparto = st.sidebar.selectbox("Comparto d'investimento", comparti_base, index=_idx_comp)
ter_fondo, rend_medio_fondo, vol_fondo, quota_ts = preset["comparti"][comparto]

under35 = eta < 35
contrib_az_pct = preset["contrib_azienda_u35_pct"] if under35 else preset["contrib_azienda_pct"]

st.sidebar.caption(
    f"**{preset['fondo']} · {comparto}** — datore {contrib_az_pct*100:.2f}% "
    f"(sui minimi+scatti) · tu min {preset['contrib_lav_pct']*100:.2f}% · "
    f"TFR {preset['tfr_pct']*100:.2f}% · TER {ter_fondo*100:.2f}%/anno · "
    f"rend. atteso {rend_medio_fondo*100:.1f}% (vol. {vol_fondo*100:.0f}%)"
)

vers_vol_extra = st.sidebar.number_input(
    "Versamento volontario AGGIUNTIVO annuo (€)", min_value=0, value=1000, step=100,
    help="Oltre al contributo minimo previsto dal CCNL. Deducibile dall'IRPEF.",
)

st.sidebar.header("4. Performance simulata (Fondo)")
metodo_resampling = st.sidebar.radio(
    "Metodo di resampling del fondo",
    ["Block-bootstrap mensile", "Bootstrap annuale"],
    index=0,
    help="I rendimenti del fondo vengono SEMPRE dal ricampionamento dello storico "
         "reale del comparto (nessun GBM). Il block-bootstrap mensile ricampiona "
         "blocchi di 12 mesi consecutivi (più dati, preserva la sequenza); il "
         "bootstrap annuale ricampiona direttamente i rendimenti di ogni anno.",
)
usa_mensile = metodo_resampling.startswith("Block")
block_mesi = 12
if usa_mensile:
    block_mesi = st.sidebar.number_input(
        "Lunghezza blocco (mesi)", min_value=3, max_value=24, value=12, step=1,
        help="Dimensione del blocco contiguo ricampionato. 12 = un anno intero.",
    )

st.sidebar.caption("Banda P10–P90 mostrata su tutte le curve (200 scenari).")
percentile_perf = st.sidebar.slider(
    "Percentile della linea centrale", 5, 95, 50, 5,
    help="P5 = scenario molto sfortunato · P50 = mediano · P95 = molto fortunato. "
         "La banda P10–P90 attorno resta sempre visibile.",
)

st.sidebar.header("5. PAC (ETF)")
versamento_pac = st.sidebar.number_input("Versamento PAC Annuo (€)", min_value=0, value=3445, step=100)

modo_pac = st.sidebar.radio(
    "Modalità PAC",
    ["Semplice (parametri manuali)", "Portafoglio ticker (dati storici)"],
    index=0,
    help="Con i ticker, rendimenti/volatilità/correlazioni vengono stimati dallo "
         "storico Yahoo Finance e la simulazione usa asset correlati via Cholesky.",
)
usa_portafoglio = modo_pac.startswith("Portafoglio")

rend_medio_pac, vol_pac = 0.07, 0.15   # fallback
tickers_input = pesi_input = ""
anni_storico, override_rend, rend_override_val = 10, False, None

if usa_portafoglio:
    st.sidebar.markdown("**Catalogo ETF predefiniti (solo accumulazione UCITS)**")
    st.sidebar.caption(
        "Seleziona uno o più ETF dalla legenda, oppure aggiungine a mano. "
        "I ticker manuali NON in whitelist vengono segnalati (dist/acc/UCITS)."
    )

    selezione_catalogo = {}
    for categoria, etfs in CATALOGO_ETF.items():
        scelti = st.sidebar.multiselect(categoria, list(etfs.keys()), key=f"cat_{categoria}")
        for nome in scelti:
            selezione_catalogo[etfs[nome]] = nome

    tickers_manuali_str = st.sidebar.text_input(
        "Aggiungi ticker manuale (separati da virgola, opzionale)", value="",
        help="Per ETF non in catalogo o AZIONI SINGOLE (es. AAPL, ENI.MI). "
             "Le azioni sono ammesse ma molto più volatili di un ETF: l'app "
             "ti avviserà. Per gli ETF verifica che siano ad accumulo UCITS.",
    )
    tickers_manuali = [t.strip().upper() for t in tickers_manuali_str.split(",") if t.strip()]

    tickers_scelti = list(selezione_catalogo.keys())
    for t in tickers_manuali:
        if t not in tickers_scelti:
            tickers_scelti.append(t)

    # --- CONTROLLO ACCUMULAZIONE / UCITS sui ticker scelti ---
    avvisi_ticker = []
    for t in tickers_scelti:
        stato, nota = classifica_ticker(t)
        if stato == "warn":
            avvisi_ticker.append(f"⚠️ **{t}**: {nota}")
        elif stato == "sconosciuto":
            avvisi_ticker.append(f"❓ **{t}**: {nota}")
    if avvisi_ticker:
        st.sidebar.warning(
            "Controllo accumulazione/UCITS:\n\n" + "\n\n".join(avvisi_ticker)
        )

    if len(tickers_scelti) == 0:
        st.sidebar.warning("Nessun ticker selezionato: scegline almeno uno.")

    st.sidebar.markdown("**Pesi (%) per ciascun ticker selezionato**")
    pesi_dict = {}
    peso_default = round(100 / len(tickers_scelti), 1) if tickers_scelti else 0.0
    for t in tickers_scelti:
        etichetta = TICKER_TO_NOME.get(t, t)
        pesi_dict[t] = st.sidebar.number_input(
            f"Peso {etichetta}", min_value=0.0, max_value=100.0,
            value=peso_default, step=1.0, key=f"peso_{t}",
        )

    somma_pesi = sum(pesi_dict.values())
    if tickers_scelti:
        if abs(somma_pesi - 100.0) > 0.01:
            st.sidebar.caption(f"Somma pesi: {somma_pesi:.1f}% — normalizzata a 100%.")
        else:
            st.sidebar.caption(f"Somma pesi: {somma_pesi:.1f}% ✓")

    tickers_input = ", ".join(tickers_scelti)
    pesi_input = ", ".join(str(pesi_dict[t]) for t in tickers_scelti)

    with st.sidebar.expander("📖 Legenda completa ETF disponibili"):
        for categoria, etfs in CATALOGO_ETF.items():
            st.markdown(f"**{categoria}**")
            for nome, ticker in etfs.items():
                st.caption(f"`{ticker}` — {nome}")

    anni_storico = st.sidebar.slider("Anni di storico per la stima", 5, 20, 10)
    override_rend = st.sidebar.checkbox(
        "Correggi a mano il rendimento atteso", value=True,
        help="Consigliato: il rendimento medio storico è un cattivo predittore "
             "del futuro. Volatilità e correlazioni restano quelle storiche.",
    )
    if override_rend:
        rend_override_val = st.sidebar.slider(
            "Rendimento atteso portafoglio (%)", 1.0, 12.0, 6.0, 0.1) / 100
else:
    rend_medio_pac = st.sidebar.slider("Rendimento medio atteso PAC (%)", 1.0, 12.0, 7.0, 0.1) / 100
    vol_pac        = st.sidebar.slider("Volatilità PAC (%)", 5.0, 25.0, 15.0, 0.5) / 100

ter_pac          = st.sidebar.number_input("TER PAC (%)", value=0.20, step=0.01) / 100
tassa_uscita_pac = st.sidebar.slider("Tassazione Plusvalenze PAC (%)", 0, 26, 26)

st.sidebar.header("6. TFR in Azienda")
rend_tfr  = st.sidebar.slider("Rendimento Annuo TFR in Azienda (%)", 0.0, 7.0, 2.5, 0.1,
                              help="Rivalutazione legale: 1,5% + 75% inflazione")/100
tassa_tfr = st.sidebar.slider("Tassazione TFR Uscita (%)", 23, 43, 27)

st.sidebar.header("7. Uscita dal fondo")
anni_gia_iscritto = st.sidebar.number_input(
    "Anni di adesione già maturati al fondo", min_value=0, max_value=40, value=0, step=1,
    help="Servono per l'aliquota di uscita agevolata (sconto dopo il 15° anno)",
)
motivo_uscita = st.sidebar.selectbox(
    "Motivo di uscita dal fondo",
    [
        "Prestazione pensionistica / causali agevolate (9–15%)",
        "Riscatto/anticipazione ordinaria (23%)",
    ],
    index=0,
)
uscita_ordinaria = motivo_uscita.startswith("Riscatto")
usa_entrambi = st.sidebar.checkbox("Uso sia Fondo che PAC (somma senza TFR)", value=True)


# ---------------------------------------------------------------------------
# IRPEF
# ---------------------------------------------------------------------------
LIMITE_DEDUCIBILITA = 5164.57

def aliquota_marginale(imponibile: float) -> float:
    if imponibile <= 28_000:
        return 0.23
    elif imponibile <= 50_000:
        return 0.35
    else:
        return 0.43

def calcola_irpef(imponibile: float) -> float:
    imponibile = max(0.0, imponibile)
    if imponibile <= 28_000:
        return imponibile * 0.23
    elif imponibile <= 50_000:
        return 28_000 * 0.23 + (imponibile - 28_000) * 0.35
    else:
        return 28_000 * 0.23 + 22_000 * 0.35 + (imponibile - 50_000) * 0.43


# ---------------------------------------------------------------------------
# ALIQUOTA DI USCITA DEL FONDO PENSIONE
# ---------------------------------------------------------------------------
def aliquota_uscita_fondo(anni_adesione_totali: int, ordinaria: bool = False) -> float:
    if ordinaria:
        return 0.23
    if anni_adesione_totali <= 15:
        return 0.15
    sconto = min(anni_adesione_totali - 15, 20) * 0.003
    return max(0.09, 0.15 - sconto)


# ---------------------------------------------------------------------------
# GENERAZIONE 1000 SIMULAZIONI DI CARRIERA
# ---------------------------------------------------------------------------
@st.cache_data
def genera_scenari(profilo: str, coeff: float, crescita_base: float,
                   n: int = 1000, seed: int = 42):
    rng = np.random.default_rng(seed)
    range_profilo = {"Moderata": (0.02, 0.05), "Media": (0.03, 0.07), "Spinta": (0.06, 0.10)}
    profilo_key = profilo.split(" ")[0]
    r_min, r_max = range_profilo[profilo_key]
    boost_junior = 1.35 if profilo_key == "Spinta" else 1.55

    scenari = []
    for _ in range(n):
        molt = 1.0
        percorso = [1.0]
        attesa = 0
        target = rng.integers(1, 3)
        for anno in range(1, 40):
            attesa += 1
            base_anno = max(0.0, crescita_base + rng.normal(0, 0.004))
            molt *= (1.0 + base_anno)
            if anno <= 6:
                fase_molt, min_t, max_t = boost_junior, 1, 2
            elif anno <= 10:
                fase_molt, min_t, max_t = 1.05, 2, 3
            elif anno <= 18:
                fase_molt, min_t, max_t = 0.45, 3, 4
            else:
                fase_molt, min_t, max_t = 0.30, 4, 6
            prob_cambio = 0.15 if anno <= 10 else (0.08 if anno <= 18 else 0.04)
            cambio = (anno > 3) and (rng.random() < prob_cambio)
            if attesa >= target or cambio:
                amp = r_min + rng.random() * (r_max - r_min)
                amp *= fase_molt * coeff
                amp += rng.normal(0, 0.006)
                amp = max(0.0, amp)
                molt *= (1.0 + amp)
                attesa = 0
                target = rng.integers(min_t, max_t + 1)
            percorso.append(molt)
        scenari.append(percorso)
    return scenari


# ---------------------------------------------------------------------------
# GENERAZIONE TRAIETTORIE DI RENDIMENTO — TUTTE MENSILI (n x durata*12)
# ---------------------------------------------------------------------------
# Il motore del montante ora lavora MESE PER MESE: i versamenti vengono
# spalmati su 12 rate e ogni rata rende solo per i mesi residui. Tutti i
# generatori quindi restituiscono matrici di rendimenti MENSILI.

@st.cache_data
def genera_rendimenti_gbm(rend_medio: float, vol: float, durata: int,
                          n: int = 200, seed: int = 7):
    """
    GBM lognormale MENSILE. `rend_medio` e `vol` restano parametri ANNUI
    (come esposti in sidebar); vengono convertiti in parametri mensili
    (media geometrica mensile, vol/sqrt(12)). Ritorna (n x durata*12).
    """
    rng = np.random.default_rng(seed)
    rend_m = (1 + rend_medio) ** (1 / 12) - 1
    vol_m = vol / np.sqrt(12)
    sigma = np.sqrt(np.log(1 + (vol_m**2) / ((1 + rend_m)**2)))
    mu = np.log(1 + rend_m) - 0.5 * sigma**2
    shocks = rng.normal(mu, sigma, size=(n, durata * 12))
    return np.exp(shocks) - 1.0


# ---------------------------------------------------------------------------
# BRANCH: BOOTSTRAP STORICO DEI RENDIMENTI DI COMPARTO
# ---------------------------------------------------------------------------
@st.cache_data
def genera_rendimenti_bootstrap(serie_storica: tuple, durata: int,
                                n: int = 200, seed: int = 21):
    """
    Bootstrap iid sui rendimenti ANNUI storici reali del comparto. Ogni anno
    ricampionato viene poi spalmato in 12 rendimenti mensili equivalenti
    ((1+r)^(1/12)-1), così il motore mensile può usarlo direttamente.
    Ritorna (n x durata*12).
    """
    serie = np.array(serie_storica, dtype=float)
    if serie.size == 0:
        raise ValueError("Serie storica del comparto vuota.")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, serie.size, size=(n, durata))
    annui = serie[idx]                              # (n, durata)
    mensili = (1 + annui) ** (1 / 12) - 1           # (n, durata)
    return np.repeat(mensili, 12, axis=1)           # (n, durata*12)


@st.cache_data
def genera_rendimenti_block_bootstrap(serie_mensile: tuple, durata: int,
                                      block: int = 12, n: int = 200, seed: int = 33):
    """
    BLOCK-BOOTSTRAP MENSILE. Ricampiona blocchi CONTIGUI di `block` mesi dai
    rendimenti mensili storici reali del comparto (bootstrap circolare, con
    wrap-around) e li concatena fino a coprire `durata` anni.

    Rispetto al bootstrap annuale iid, preserva la struttura temporale interna
    (autocorrelazione, sequenze di mesi buoni/cattivi) e sfrutta MOLTE più
    osservazioni. Ritorna direttamente i rendimenti MENSILI (n x durata*12).
    """
    serie = np.array(serie_mensile, dtype=float)
    m = serie.size
    if m < block:
        raise ValueError(f"Servono almeno {block} mesi, disponibili {m}.")
    rng = np.random.default_rng(seed)
    mesi_tot = durata * 12
    out = np.empty((n, mesi_tot))
    n_blocchi = int(np.ceil(mesi_tot / block))
    for s in range(n):
        start = rng.integers(0, m, size=n_blocchi)
        path = np.concatenate([serie[(st + np.arange(block)) % m] for st in start])[:mesi_tot]
        out[s] = path
    return out


def mensili_ad_annui(mat_mensile: np.ndarray) -> np.ndarray:
    """Compone una matrice di rendimenti mensili (n x anni*12) in annui (n x anni)."""
    n, mesi = mat_mensile.shape
    anni = mesi // 12
    return np.prod(1 + mat_mensile[:, :anni * 12].reshape(n, anni, 12), axis=2) - 1


def rendimento_netto_comparto(r, ter, quota_ts):
    """
    Rende netto annuo a livello di comparto, coerente col motore del montante:
    tassa 20%/12,5% (media pesata sulla quota in titoli di Stato) applicata al
    rendimento, poi TER. Vale anche per r<0 (credito d'imposta implicito).
    """
    aliq = 0.20 * (1 - quota_ts) + 0.125 * quota_ts
    r = np.asarray(r, dtype=float)
    return (1 + r * (1 - aliq)) * (1 - ter) - 1


def seleziona_traiettoria_per_percentile(rendimenti: np.ndarray, percentile: int):
    montanti = np.prod(1 + rendimenti, axis=1)
    ordine = np.argsort(montanti)
    idx = int(round((percentile / 100) * (len(ordine) - 1)))
    return rendimenti[ordine[idx]]


# ---------------------------------------------------------------------------
# PORTAFOGLIO A TICKER: download storico, stima parametri, Cholesky
# ---------------------------------------------------------------------------
def parse_ticker_pesi(tickers_str: str, pesi_str: str):
    tickers = [t.strip().upper() for t in tickers_str.split(",") if t.strip()]
    pesi_raw = [p.strip() for p in pesi_str.split(",") if p.strip()]
    if len(tickers) == 0:
        raise ValueError("Inserisci almeno un ticker.")
    if len(pesi_raw) != len(tickers):
        raise ValueError(f"Hai {len(tickers)} ticker ma {len(pesi_raw)} pesi.")
    pesi = np.array([float(p) for p in pesi_raw])
    if pesi.sum() <= 0:
        raise ValueError("La somma dei pesi deve essere positiva.")
    pesi = pesi / pesi.sum()
    return tickers, pesi


@st.cache_data(show_spinner=False)
def scarica_prezzi_mensili(tickers: tuple, anni: int):
    import yfinance as yf
    import pandas as pd
    from datetime import date
    from dateutil.relativedelta import relativedelta

    end = date.today()
    start = end - relativedelta(years=anni)

    serie = {}
    for t in tickers:
        data = yf.download(t, start=start.isoformat(), end=end.isoformat(),
                           progress=False, auto_adjust=False, actions=False)
        if data is None or data.empty:
            raise ValueError(f"Nessun dato scaricato per '{t}'. Verifica il ticker su Yahoo.")
        if "Close" in data.columns:
            col_data = data["Close"]
        else:
            col_data = data.iloc[:, 0]
        if isinstance(col_data, pd.DataFrame):
            col_data = col_data.iloc[:, 0]
        serie[t] = col_data.resample("ME").last()

    df = pd.DataFrame(serie).dropna()
    if len(df) < 24:
        raise ValueError(
            f"Storico comune troppo corto ({len(df)} mesi): riduci gli anni o "
            f"verifica i ticker."
        )
    return df


def stima_parametri_portafoglio(prezzi_df: pd.DataFrame, pesi: np.ndarray):
    rend_mensili = prezzi_df.pct_change().dropna()
    media_mensile = rend_mensili.mean().values
    cov_mensile = rend_mensili.cov().values
    corr = rend_mensili.corr().values
    rend_annuo_asset = (1 + media_mensile) ** 12 - 1
    vol_annua_asset = rend_mensili.std().values * np.sqrt(12)
    rend_portafoglio = float(np.dot(pesi, rend_annuo_asset))
    vol_portafoglio = float(np.sqrt(pesi @ (cov_mensile * 12) @ pesi))
    cov_reg = cov_mensile + np.eye(len(pesi)) * 1e-10
    L = np.linalg.cholesky(cov_reg)
    return {
        "tickers": list(prezzi_df.columns),
        "rend_annuo_asset": rend_annuo_asset,
        "vol_annua_asset": vol_annua_asset,
        "corr": corr,
        "media_mensile": media_mensile,
        "cholesky_mensile": L,
        "rend_portafoglio": rend_portafoglio,
        "vol_portafoglio": vol_portafoglio,
        "n_mesi_storico": len(rend_mensili),
        "prezzi_df": prezzi_df,
    }


@st.cache_data(show_spinner=False)
def genera_rendimenti_portafoglio_gbm(media_mensile, cholesky_mensile, pesi,
                                      durata_anni: int, rend_override=None,
                                      n: int = 200, seed: int = 13):
    """
    Traiettorie MENSILI del portafoglio (n x durata*12) con shock correlati
    (Cholesky). Se rend_override è dato, il drift viene TRASLATO (non scalato)
    di una costante uguale per tutti gli asset, così da centrare il rendimento
    atteso del portafoglio sull'override senza mai invertire il segno dei
    singoli asset (bug del vecchio approccio moltiplicativo quando lo storico
    era negativo).
    """
    rng = np.random.default_rng(seed)
    n_asset = len(pesi)
    mesi_tot = durata_anni * 12
    drift = media_mensile.copy()
    if rend_override is not None:
        target_m = (1 + rend_override) ** (1 / 12) - 1        # drift mensile obiettivo (portafoglio)
        attuale_m = float(np.dot(pesi, drift))                 # drift mensile attuale (portafoglio)
        drift = drift + (target_m - attuale_m)                 # shift additivo uniforme

    traiettorie = np.zeros((n, mesi_tot))
    for s in range(n):
        z = rng.standard_normal((mesi_tot, n_asset))
        shock_mensili = z @ cholesky_mensile.T
        rend_mensili_asset = drift + shock_mensili
        traiettorie[s] = rend_mensili_asset @ pesi
    return traiettorie


# ---------------------------------------------------------------------------
# COSTRUZIONE DELLO SCHEDULE ANNO-PER-ANNO (livello, CCNL, comparto, disoccup.)
# ---------------------------------------------------------------------------
def costruisci_schedule(durata, ccnl_start, livello_start, comparto_start,
                        eta, anni_pregressi_scatti, superminimo_annuo,
                        premio_annuo, crescita_base, passaggi_livello,
                        cambi_ccnl, anni_disoccupato):
    """
    Ritorna una lista lunga `durata`. Ogni elemento descrive il CCNL/livello/
    comparto ATTIVO in quell'anno e i parametri contributivi derivati, così che
    il motore possa gestire cambi di livello, cambi di CCNL e disoccupazione
    semplicemente leggendo lo schedule.
    """
    # eventi (anno_da, tipo, payload) applicati cumulativamente
    eventi = []
    for anno_da, liv in passaggi_livello:
        eventi.append((anno_da, "livello", liv))
    for anno_da, ccnl_n, liv_n, comp_n in cambi_ccnl:
        eventi.append((anno_da, "ccnl", (ccnl_n, liv_n, comp_n)))
    eventi.sort(key=lambda x: x[0])

    sched = []
    for a in range(durata):
        anno = a + 1
        ccnl_att, liv_att, comp_att = ccnl_start, livello_start, comparto_start
        anno_ultimo_cambio_ccnl = 0   # 0 = nessun cambio (si parte dal CCNL iniziale)
        for anno_da, tipo, payload in eventi:
            if anno_da <= anno:
                if tipo == "livello":
                    liv_att = payload
                else:
                    ccnl_att, liv_att, comp_att = payload
                    anno_ultimo_cambio_ccnl = anno_da
        preset_a = CCNL_PRESET[ccnl_att]
        # comparto di ripiego se il nome non esiste nel nuovo fondo
        if comp_att not in preset_a["comparti"]:
            comp_att = list(preset_a["comparti"].keys())[-1]

        mens_a = preset_a["mensilita"]
        minimo_mensile_a = preset_a["livelli"][liv_att]
        minimo_annuo_a = minimo_mensile_a * mens_a
        scatto_val_liv_a = preset_a.get("scatti_valore_livello", {}).get(
            liv_att, preset_a["scatto_valore"])
        scatto_annuo_a = scatto_val_liv_a * mens_a
        freq_a = preset_a["scatto_ogni_anni"]
        max_a = preset_a["scatti_max"]

        eta_corrente = eta + a
        u35 = eta_corrente < 35
        ca_pct_a = preset_a["contrib_azienda_u35_pct"] if u35 else preset_a["contrib_azienda_pct"]
        lav_pct_a = preset_a["contrib_lav_pct"]
        tfr_pct_a = preset_a["tfr_pct"]

        ter_f_a, rend_a, vol_a, quota_ts_a = preset_a["comparti"][comp_att]
        costo_fisso_a = preset_a["costo_fisso"]

        # --- SCATTI DI ANZIANITÀ ---
        # Regola: gli scatti maturano nel rapporto di lavoro corrente. Un
        # CAMBIO DI CCNL (cambio azienda/settore) azzera l'anzianità: gli
        # scatti pregressi e quelli maturati prima del cambio SI PERDONO e si
        # ricomincia a maturare da zero nel nuovo contratto. I passaggi di
        # LIVELLO (promozione interna) invece NON azzerano nulla.
        # Il totale è sempre limitato a scatti_max del CCNL corrente: se parti
        # con 2 pregressi su max 5, potrai maturarne al più altri 3.
        if anno_ultimo_cambio_ccnl == 0:
            # nessun cambio: pregressi + anzianità simulata
            anni_servizio = anni_pregressi_scatti * freq_a + anno
        else:
            # anzianità solo dall'anno del cambio in poi (pregressi persi)
            anni_servizio = anno - anno_ultimo_cambio_ccnl + 1
        scatti_maturati = min(max_a, anni_servizio // freq_a)
        base_teorica = minimo_annuo_a + scatti_maturati * scatto_annuo_a
        base_contrib_a = base_teorica * ((1 + crescita_base) ** a)

        # base RAL (anno 1 equivalente del segmento), scalata poi dalla carriera.
        # Dopo un cambio CCNL gli scatti pregressi spariscono anche dalla RAL.
        scatti_in_ral = anni_pregressi_scatti if anno_ultimo_cambio_ccnl == 0 else 0
        ral_base_eff_a = (minimo_annuo_a + scatti_in_ral * scatto_annuo_a
                          + superminimo_annuo + premio_annuo)

        occupato = anno not in anni_disoccupato

        sched.append({
            "anno": anno,
            "ccnl": ccnl_att, "livello": liv_att, "comparto": comp_att,
            "fondo": preset_a["fondo"], "comparto_key": (preset_a["fondo"], comp_att),
            "mensilita": mens_a,
            "ca_pct": ca_pct_a, "lav_pct": lav_pct_a, "tfr_pct": tfr_pct_a,
            "ter_f": ter_f_a, "costo_fisso_f": costo_fisso_a, "quota_ts": quota_ts_a,
            "rend_medio": rend_a, "vol": vol_a,
            "base_contrib": base_contrib_a if occupato else 0.0,
            "ral_base_eff": ral_base_eff_a,
            "scatti": scatti_maturati,
            "occupato": occupato,
        })
    return sched


# ---------------------------------------------------------------------------
# MOTORE DI SIMULAZIONE DEL CAPITALE (schedule-driven)
# ---------------------------------------------------------------------------
def simula_capitale(fattori, rend_fondo_mensili, rend_pac_mensili, sched, scal) -> pd.DataFrame:
    """
    Simula il montante MESE PER MESE. `rend_fondo_mensili` e `rend_pac_mensili`
    sono traiettorie di rendimenti mensili lunghe durata*12 (già coerenti con
    lo schedule dei comparti per il fondo). I versamenti annui vengono divisi
    in 12 rate: ogni rata rende solo per i mesi residui — coerente con un PAC
    e con i contributi mensili reali al fondo (fix della sovrastima da
    versamento "tutto a gennaio").
    """
    ral_override = scal["ral_override"]
    ral_manuale = scal["ral_manuale"]
    vol_extra = scal["vers_vol_extra"]
    vp0 = scal["vp"]
    ter_p = scal["ter_p"]
    tp = scal["tp"] / 100
    rt = scal["rt"]
    tt = scal["tt"] / 100
    anni_pregressi = scal["anni_pregressi"]
    uscita_ord = scal["uscita_ordinaria"]

    cap_fondo = float(scal.get("cap_iniziale_fondo", 0.0))
    cap_pac = float(scal.get("cap_iniziale_pac", 0.0))
    versato_pac_cum = float(scal.get("cap_iniziale_pac", 0.0))
    cap_tfr = 0.0
    rows = []

    for a, f in enumerate(fattori):
        s = sched[a]
        anno = a + 1
        occupato = s["occupato"]

        # RAL: override manuale (se attivo) solo mentre si è occupati
        if occupato:
            ral_curr = ral_manuale * f if ral_override else s["ral_base_eff"] * f
        else:
            ral_curr = 0.0

        base_contrib = s["base_contrib"]  # già 0 se disoccupato
        aliq_rend_fondo = 0.20 * (1 - s["quota_ts"]) + 0.125 * s["quota_ts"]

        # Importi ANNUI (per la tabella e l'IRPEF)
        tfr_curr = ral_curr * s["tfr_pct"] if occupato else 0.0
        ca_curr = base_contrib * s["ca_pct"]
        vol_min = base_contrib * s["lav_pct"]
        vf_curr = vol_min + (vol_extra if occupato else 0.0)
        vp_curr = (vp0 * f) if occupato else 0.0

        # Deduzione IRPEF (solo se occupato e c'è reddito)
        if occupato and (vf_curr + ca_curr) > 0:
            deducibile = min(vf_curr + ca_curr, LIMITE_DEDUCIBILITA)
            aliq_marg = aliquota_marginale(ral_curr)
            quota_lav = vf_curr / (vf_curr + ca_curr)
            risparmio_anno = deducibile * aliq_marg * quota_lav
        else:
            risparmio_anno = 0.0

        # --- CICLO MENSILE: versamenti in 12 rate, rendimento mese per mese ---
        # Ogni rata prende solo il rendimento dei mesi RESIDUI dell'anno (fix
        # della vecchia versione che dava un anno intero di rendimento a tutto
        # il versamento annuo). TER e rivalutazione TFR convertiti in mensili.
        rata_fondo = (vf_curr + tfr_curr + ca_curr) / 12.0
        rata_pac = vp_curr / 12.0
        rata_tfr = tfr_curr / 12.0
        ter_f_m = 1 - (1 - s["ter_f"]) ** (1 / 12)
        ter_p_m = 1 - (1 - ter_p) ** (1 / 12)
        rt_m = (1 + rt) ** (1 / 12) - 1

        for mese in range(12):
            r_f = rend_fondo_mensili[a * 12 + mese]
            r_p = rend_pac_mensili[a * 12 + mese]

            # FONDO: versamento a inizio mese, rendimento tassato, poi TER
            cap_fondo += rata_fondo
            cap_fondo += cap_fondo * r_f * (1 - aliq_rend_fondo)
            cap_fondo *= (1 - ter_f_m)

            # PAC: versamento a inizio mese, rendimento, TER
            versato_pac_cum += rata_pac
            cap_pac += rata_pac
            cap_pac *= (1 + r_p) * (1 - ter_p_m)

            # TFR in azienda: accantonamento mensile + rivalutazione mensile
            cap_tfr += rata_tfr
            cap_tfr *= (1 + rt_m)

        # Costo fisso amministrativo del fondo: una volta l'anno
        cap_fondo = max(0.0, cap_fondo - s["costo_fisso_f"])

        # --- Valori netti a uscita ---
        anni_adesione = anni_pregressi + anno
        aliq_uscita = aliquota_uscita_fondo(anni_adesione, ordinaria=uscita_ord)
        netto_fondo = cap_fondo * (1 - aliq_uscita)
        plusval_pac = max(0.0, cap_pac - versato_pac_cum)
        netto_pac = cap_pac - plusval_pac * tp
        netto_tfr = cap_tfr * (1 - tt)

        rows.append({
            "Anno": anno,
            "CCNL": s["ccnl"], "Livello": s["livello"], "Comparto": s["comparto"],
            "Scatti": s["scatti"],
            "Occupato": "Sì" if occupato else "No",
            "RAL (€)": ral_curr,
            "Contrib. Min. CCNL (€)": vol_min,
            "Vers. Volontario (€)": (vol_extra if occupato else 0.0),
            "TFR al Fondo (€)": tfr_curr,
            "Contrib. Aziendale (€)": ca_curr,
            "Risparmio IRPEF (€)": risparmio_anno,
            "PAC annuo (€)": vp_curr,
            "Aliq. uscita fondo (%)": aliq_uscita * 100,
            "Fondo Netto (€)": netto_fondo,
            "PAC + TFR Netto (€)": netto_pac + netto_tfr,
            "PAC Netto (€)": netto_pac,
            "Fondo + PAC Netto (€)": netto_fondo + netto_pac,
        })
    return pd.DataFrame(rows)


def calcola_bande(fattori, rend_fondo_mat, rend_pac_mat, sched, scal, n_band=200):
    """
    Esegue il motore su n_band scenari di RENDIMENTO (carriera fissata alla
    mediana) e restituisce P10/P50/P90 anno-per-anno per ogni curva. È qui che
    nasce la banda GBM 10–90 richiesta su TUTTE le curve (Fondo, solo PAC,
    PAC+TFR, Fondo+PAC).
    """
    curve = ["Fondo Netto (€)", "PAC Netto (€)", "PAC + TFR Netto (€)", "Fondo + PAC Netto (€)"]
    acc = {c: [] for c in curve}
    m = min(n_band, rend_fondo_mat.shape[0], rend_pac_mat.shape[0])
    for i in range(m):
        d = simula_capitale(fattori, rend_fondo_mat[i], rend_pac_mat[i], sched, scal)
        for c in curve:
            acc[c].append(d[c].tolist())
    bande = {}
    for c in curve:
        arr = np.array(acc[c])
        bande[c] = {
            "p10": np.percentile(arr, 10, axis=0),
            "p50": np.percentile(arr, 50, axis=0),
            "p90": np.percentile(arr, 90, axis=0),
        }
    return bande


# ---------------------------------------------------------------------------
# ESECUZIONE
# ---------------------------------------------------------------------------
scatti_valore_annuo = anni_anzianita_pregressi * scatto_valore_livello * mensilita
base_contrib_iniziale = minimo_annuo + scatti_valore_annuo
superminimo_annuo = superminimo_mensile * mensilita
ral_auto = base_contrib_iniziale + superminimo_annuo + premio_produzione_annuo
ral_override = ral_manuale > 0
ral = ral_manuale if ral_override else ral_auto

coeff_totale = COEFF_LAVORATORE[tipo_lavoratore]
scenari = genera_scenari(profilo_crescita, coeff_totale, crescita_base, n=1000)

# --- Schedule anno-per-anno ---
sched = costruisci_schedule(
    durata, ccnl_scelto, livello, comparto, eta, anni_anzianita_pregressi,
    superminimo_annuo, premio_produzione_annuo, crescita_base,
    passaggi_livello if usa_passaggi_livello else [],
    cambi_ccnl if usa_cambio_ccnl else [],
    anni_disoccupato,
)

N_BAND = 200

# --- Traiettorie di rendimento del FONDO (per comparto, poi spliced) ---
# Ogni comparto attivo nello schedule genera una propria matrice (n x durata);
# la matrice finale prende, colonna per colonna (anno per anno), i rendimenti
# del comparto attivo in quell'anno. Così un cambio CCNL/comparto a metà
# carriera cambia davvero il motore di rendimento del fondo.
comparto_keys = sorted({s["comparto_key"] for s in sched})
avvisi_corti = []       # comparti con storico annuale troppo corto
mancanti = []           # comparti senza dati per il metodo scelto (GBM rimosso)
mat_per_comparto = {}
for ki, key in enumerate(comparto_keys):
    fondo_k, comp_k = key
    # seed decorrelato per comparto (evita traiettorie identiche tra comparti
    # in caso di cambio CCNL/comparto a metà carriera)
    if usa_mensile:
        if mensile_disponibile(fondo_k, comp_k):
            serie = tuple(STORICO_MENSILE[fondo_k][comp_k])
            mat_per_comparto[key] = genera_rendimenti_block_bootstrap(
                serie, durata, block=int(block_mesi), n=N_BAND, seed=33 + ki)
        else:
            mancanti.append(f"{fondo_k} · {comp_k} (serie mensile)")
    else:
        if annuale_disponibile(fondo_k, comp_k):
            serie = tuple(STORICO_ANNUALE[fondo_k][comp_k])
            if len(serie) < 8:
                avvisi_corti.append(f"{fondo_k} · {comp_k} ({len(serie)} anni)")
            mat_per_comparto[key] = genera_rendimenti_bootstrap(serie, durata, n=N_BAND, seed=21 + ki)
        else:
            mancanti.append(f"{fondo_k} · {comp_k} (serie annuale)")

if mancanti:
    st.error(
        "**Dati storici mancanti** per: " + ", ".join(mancanti) + ".\n\n"
        "Il GBM è stato rimosso dal fondo: i rendimenti provengono solo dal "
        "resampling dello storico reale. Popola `STORICO_MENSILE` / "
        "`STORICO_ANNUALE` per questi comparti (o scegli un CCNL/comparto già "
        "coperto, es. Cometa) per continuare."
    )
    st.stop()

rend_fondo_mat = np.empty((N_BAND, durata * 12))
for a, s in enumerate(sched):
    rend_fondo_mat[:, a * 12:(a + 1) * 12] = \
        mat_per_comparto[s["comparto_key"]][:, a * 12:(a + 1) * 12]

# --- PAC: GBM parametrico / portafoglio ticker ---
portafoglio_info = None
errore_portafoglio = None
if usa_portafoglio:
    if not tickers_input.strip():
        errore_portafoglio = "Nessun ticker selezionato: usa il catalogo o inseriscine uno."
        rend_pac_mat = genera_rendimenti_gbm(0.07, 0.15, durata, n=N_BAND, seed=11)
    else:
        try:
            tickers, pesi = parse_ticker_pesi(tickers_input, pesi_input)
            prezzi_df = scarica_prezzi_mensili(tuple(tickers), anni_storico)
            portafoglio_info = stima_parametri_portafoglio(prezzi_df, pesi)
            rend_override_eff = rend_override_val if override_rend else None
            rend_pac_mat = genera_rendimenti_portafoglio_gbm(
                portafoglio_info["media_mensile"], portafoglio_info["cholesky_mensile"],
                pesi, durata, rend_override=rend_override_eff, n=N_BAND, seed=13,
            )
        except Exception as e:
            errore_portafoglio = str(e)
            rend_pac_mat = genera_rendimenti_gbm(0.07, 0.15, durata, n=N_BAND, seed=11)
else:
    rend_pac_mat = genera_rendimenti_gbm(rend_medio_pac, vol_pac, durata, n=N_BAND, seed=11)

# --- Traiettorie centrali (per la tabella e la linea centrale) ---
rend_fondo_sel = seleziona_traiettoria_per_percentile(rend_fondo_mat, percentile_perf)
rend_pac_sel = seleziona_traiettoria_per_percentile(rend_pac_mat, percentile_perf)

# --- Parametri scalari (non variano con lo schedule) ---
scal = dict(
    ral_override=ral_override, ral_manuale=ral_manuale,
    vers_vol_extra=vers_vol_extra, vp=versamento_pac,
    ter_p=ter_pac, tp=tassa_uscita_pac, rt=rend_tfr, tt=tassa_tfr,
    anni_pregressi=anni_gia_iscritto, uscita_ordinaria=uscita_ordinaria,
    cap_iniziale_fondo=capitale_iniziale_fondo,
    cap_iniziale_pac=capitale_iniziale_pac,
)

fattori_mediani = [float(np.percentile([s[a] for s in scenari], 50)) for a in range(durata)]
df_main = simula_capitale(fattori_mediani, rend_fondo_sel, rend_pac_sel, sched, scal)

# --- Bande GBM P10–P90 su tutte le curve (carriera fissa alla mediana) ---
bande = calcola_bande(fattori_mediani, rend_fondo_mat, rend_pac_mat, sched, scal, n_band=N_BAND)
anni = list(range(1, durata + 1))


# ---------------------------------------------------------------------------
# INTESTAZIONE
# ---------------------------------------------------------------------------
motore_txt = (f"Block-bootstrap mensile (blocco {int(block_mesi)} mesi)"
              if usa_mensile else "Bootstrap annuale")
st.info(
    f"**Profilo:** {tipo_lavoratore} · {ccnl_scelto} · livello {livello} · comparto {comparto}  \n"
    f"Coefficiente crescita ×{coeff_totale:.2f} · crescita di base "
    f"{crescita_base*100:.1f}%/anno · rendimenti fondo: **{motore_txt}** (storico reale)  \n"
    f"Linea centrale **P{percentile_perf}** · banda **P10–P90** su tutte le curve "
    f"({N_BAND} scenari)  \n"
    f"*Valori nominali (includono l'inflazione, coerentemente con contributi e montante).*"
)

if (not usa_mensile) and avvisi_corti:
    st.caption(
        "ℹ️ Storico REALE ma corto (bootstrap fragile, poche osservazioni): "
        + ", ".join(avvisi_corti)
        + ". Con serie brevi la banda P10–P90 dipende da pochi anni; il block-"
          "bootstrap mensile (opzionale) sfrutterebbe più dati."
    )

if usa_cambio_ccnl and cambi_ccnl:
    st.caption(
        "🔁 **Cambi CCNL pianificati:** partenza da **" + ccnl_scelto + "** → "
        + " → ".join([f"anno {a}: **{c}** ({l}, {comp})" for a, c, l, comp in cambi_ccnl])
    )
if usa_disoccupazione and anni_disoccupato:
    st.caption(
        "⏸️ **Anni di disoccupazione:** "
        + ", ".join(str(x) for x in sorted(anni_disoccupato))
        + " — nessun contributo, i capitali continuano a rendere."
    )

# --- Composizione della RAL iniziale ---
st.subheader("🧱 Composizione della RAL (Anno 1)")
if ral_override:
    rc1, rc2, rc3 = st.columns(3)
    rc1.metric("RAL inserita a mano", f"€ {ral:,.0f}")
    rc2.metric("Base contributiva fondo", f"€ {base_contrib_iniziale:,.0f}")
    rc3.metric("RAL auto (confronto)", f"€ {ral_auto:,.0f}")
else:
    rc1, rc2, rc3, rc4 = st.columns(4)
    rc1.metric("Minimo tabellare", f"€ {minimo_annuo:,.0f}")
    rc2.metric("Scatti anzianità", f"€ {scatti_valore_annuo:,.0f}")
    rc3.metric("Superminimo + premio", f"€ {superminimo_annuo + premio_produzione_annuo:,.0f}")
    rc4.metric("RAL totale", f"€ {ral:,.0f}")

st.caption(
    f"Il contributo aziendale ({contrib_az_pct*100:.2f}%) e il tuo minimo "
    f"({preset['contrib_lav_pct']*100:.2f}%) si calcolano sulla base contributiva "
    f"(minimi + scatti), non su superminimo/premio. Il TFR "
    f"({preset['tfr_pct']*100:.2f}%) è sull'intera retribuzione."
)
st.divider()


# ---------------------------------------------------------------------------
# SEZIONE COSTI DEL FONDO
# ---------------------------------------------------------------------------
st.subheader(f"💰 Struttura dei Costi — {preset['fondo']} ({comparto})")
cc1, cc2, cc3, cc4 = st.columns(4)
cc1.metric("Costo iniziale (una tantum)", f"€ {preset['costo_iniziale']:,.2f}")
cc2.metric("Costo fisso annuo", f"€ {preset['costo_fisso']:,.0f}")
cc3.metric("TER (gestione annua)", f"{ter_fondo*100:.2f}%")
aliq_rend = 0.20 * (1 - quota_ts) + 0.125 * quota_ts
cc4.metric("Tassa sui rendimenti/anno", f"{aliq_rend*100:.1f}%")

cap_medio = df_main["Fondo Netto (€)"].mean()
ter_totale_stimato = ter_fondo * cap_medio * durata
costo_fisso_totale = preset["costo_fisso"] * durata + preset["costo_iniziale"]

with st.expander("📖 Come leggere i costi del fondo"):
    st.markdown(f"""
Il fondo pensione ha **quattro tipi di costo**, tutti inclusi nella simulazione:

1. **Costo iniziale** — €{preset['costo_iniziale']:.2f} una tantum all'iscrizione.
2. **Costo fisso annuo** — €{preset['costo_fisso']:.0f}/anno. Su {durata} anni: ~€{costo_fisso_totale:,.0f}.
3. **TER** — {ter_fondo*100:.2f}%/anno del comparto *{comparto}*; è il costo che pesa
   di più nel lungo periodo (stima ~€{ter_totale_stimato:,.0f} sull'orizzonte).
4. **Tassa sui rendimenti** — 20% ordinario, 12,5% sulla quota in titoli di Stato;
   aliquota effettiva **{aliq_rend*100:.1f}%** per *{comparto}*.
""")
st.divider()


# ---------------------------------------------------------------------------
# RENDIMENTO NETTO PER ANNO DEL COMPARTO SCELTO
# ---------------------------------------------------------------------------
st.subheader(f"📗 Rendimento netto per anno — {comparto} ({preset['fondo']})")
st.caption("Netto = dopo tassa 20%/12,5% sui rendimenti e TER del comparto, "
           "coerente col motore del montante. A sinistra lo storico reale, a "
           "destra la previsione dal resampling.")

ANNO_FINE_STORICO = 2025  # tutte le serie quote arrivano a fine 2025
fondo_sel = preset["fondo"]
serie_ann_sel = STORICO_ANNUALE.get(fondo_sel, {}).get(comparto, [])

col_a, col_b = st.columns(2)

with col_a:
    st.markdown("**Storico reale (anno per anno)**")
    if serie_ann_sel:
        anni_lbl = list(range(ANNO_FINE_STORICO - len(serie_ann_sel) + 1, ANNO_FINE_STORICO + 1))
        netti_sel = rendimento_netto_comparto(serie_ann_sel, ter_fondo, quota_ts)
        df_stor = pd.DataFrame({
            "Anno": anni_lbl,
            "Lordo (%)": [r * 100 for r in serie_ann_sel],
            "Netto (%)": [float(r) * 100 for r in netti_sel],
        })
        st.dataframe(
            df_stor.style.format({"Lordo (%)": "{:+.2f}", "Netto (%)": "{:+.2f}"}),
            use_container_width=True, hide_index=True, height=300,
        )
        cagr_l = float(np.prod([1 + r for r in serie_ann_sel])) ** (1 / len(serie_ann_sel)) - 1
        cagr_n = float(np.prod([1 + float(r) for r in netti_sel])) ** (1 / len(netti_sel)) - 1
        s1, s2, s3 = st.columns(3)
        s1.metric("CAGR lordo", f"{cagr_l*100:.2f}%")
        s2.metric("CAGR netto", f"{cagr_n*100:.2f}%")
        s3.metric("Peggiore (netto)", f"{min(netti_sel)*100:+.1f}%")
        if len(serie_ann_sel) < 8:
            st.caption(f"⚠️ Solo {len(serie_ann_sel)} anni disponibili: statistiche indicative.")
    else:
        st.info("Storico annuale non disponibile per questo comparto.")

with col_b:
    st.markdown(f"**Previsione resampling** ({motore_txt})")
    key_sel = (fondo_sel, comparto)
    if key_sel in mat_per_comparto:
        # Le matrici sono MENSILI: compongo prima in rendimenti annui, poi
        # applico tassa/TER per il netto annuo.
        mat_annua = mensili_ad_annui(mat_per_comparto[key_sel])
        net_mat = rendimento_netto_comparto(mat_annua, ter_fondo, quota_ts)
        df_prev = pd.DataFrame({
            "Anno": list(range(1, durata + 1)),
            "P10 netto (%)": np.percentile(net_mat, 10, axis=0) * 100,
            "P50 netto (%)": np.percentile(net_mat, 50, axis=0) * 100,
            "P90 netto (%)": np.percentile(net_mat, 90, axis=0) * 100,
        })
        st.dataframe(
            df_prev.style.format({c: "{:+.2f}" for c in df_prev.columns if c != "Anno"}),
            use_container_width=True, hide_index=True, height=300,
        )
        st.caption(f"Rendimento netto annuo mediano simulato: "
                   f"**{np.median(net_mat)*100:+.2f}%** (su tutti anni e scenari).")
    else:
        st.info("Comparto non attivo all'anno 1 (cambio CCNL immediato?).")

st.divider()


# ---------------------------------------------------------------------------
# SEZIONE TASSAZIONE IN USCITA
# ---------------------------------------------------------------------------
st.subheader("🏛️ Tassazione in Uscita")
anni_finali = anni_gia_iscritto + durata
aliq_uscita_finale = aliquota_uscita_fondo(anni_finali, ordinaria=uscita_ordinaria)
aliq_agevolata = aliquota_uscita_fondo(anni_finali, ordinaria=False)

tc1, tc2, tc3 = st.columns(3)
tc1.metric("Anni di adesione a fine periodo", f"{anni_finali}")
tc2.metric("Aliquota uscita applicata", f"{aliq_uscita_finale*100:.1f}%")
irpef_equiv = aliquota_marginale(df_main["RAL (€)"].iloc[-1]) * 100
tc3.metric("IRPEF ordinaria (confronto)", f"{irpef_equiv:.0f}%")

if uscita_ordinaria:
    st.warning(
        f"Riscatto/anticipazione ordinaria: ritenuta **23%**. Con uscita agevolata "
        f"pagheresti **{aliq_agevolata*100:.1f}%** — differenza di circa "
        f"**€ {df_main['Fondo Netto (€)'].iloc[-1] * (0.23 - aliq_agevolata) / (1 - 0.23):,.0f}** "
        f"sul montante finale netto."
    )
st.divider()


# ---------------------------------------------------------------------------
# COSTO MENSILE NETTO
# ---------------------------------------------------------------------------
st.subheader("💳 Costo Mensile Effettivo (Anno 1)")
r0 = df_main.iloc[0]
vers_vol_anno1 = r0["Contrib. Min. CCNL (€)"] + r0["Vers. Volontario (€)"]
risparmio_anno1 = r0["Risparmio IRPEF (€)"]
ca_anno1 = r0["Contrib. Aziendale (€)"]
costo_netto_fondo_anno1 = max(0.0, vers_vol_anno1 - risparmio_anno1)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Costo netto fondo/mese", f"€ {costo_netto_fondo_anno1/mensilita:,.0f}")
m2.metric("Costo PAC/mese", f"€ {versamento_pac/mensilita:,.0f}")
m3.metric("Totale investito/mese", f"€ {(costo_netto_fondo_anno1 + versamento_pac)/mensilita:,.0f}")
m4.metric("Contributo azienda (gratis)/anno", f"€ {ca_anno1:,.0f}")
st.divider()


# ---------------------------------------------------------------------------
# SEZIONE PORTAFOGLIO A TICKER (se attivo)
# ---------------------------------------------------------------------------
if usa_portafoglio:
    st.subheader("📈 Portafoglio PAC a Ticker")
    if not tickers_input.strip():
        st.warning("Nessun ticker selezionato. Uso GBM di fallback (7% / 15%).")
    elif errore_portafoglio:
        st.error(f"Impossibile scaricare/stimare il portafoglio: {errore_portafoglio}. "
                 f"Uso GBM di fallback (7% / 15%).")
    else:
        pi = portafoglio_info
        # Ricontrollo accumulazione/UCITS sui ticker effettivamente usati
        note_acc = []
        for t in pi["tickers"]:
            stato, nota = classifica_ticker(t)
            if stato != "ok":
                note_acc.append(f"{'⚠️' if stato=='warn' else '❓'} **{t}** — {nota}")
        if note_acc:
            st.warning("Verifica accumulazione/UCITS:\n\n" + "\n\n".join(note_acc))

        # Avviso basato sui DATI: asset con volatilità annua alta (tipico di
        # azioni singole) rendono la stima storica poco affidabile e allargano
        # molto la banda P10-P90.
        SOGLIA_VOL_ALTA = 0.25
        vol_alte = [
            f"**{t}** ({v*100:.0f}%/anno)"
            for t, v in zip(pi["tickers"], pi["vol_annua_asset"])
            if v > SOGLIA_VOL_ALTA
        ]
        if vol_alte:
            st.warning(
                "🎢 **Alta volatilità rilevata** per: " + ", ".join(vol_alte) +
                f" (soglia {SOGLIA_VOL_ALTA*100:.0f}%). Tipico di azioni singole "
                "o ETF settoriali/leva: rendimento e rischio stimati da un solo "
                "titolo sono poco affidabili e possono compromettere l'analisi "
                "di lungo periodo. Considera un peso ridotto o un ETF "
                "diversificato, e valuta con prudenza la banda P10–P90."
            )

        pc1, pc2, pc3 = st.columns(3)
        pc1.metric("Rendimento storico annuo (composto)", f"{pi['rend_portafoglio']*100:.2f}%")
        pc2.metric("Volatilità storica annua", f"{pi['vol_portafoglio']*100:.2f}%")
        pc3.metric("Asset nel portafoglio", f"{len(pi['tickers'])}")

        if override_rend:
            st.info(f"Rendimento atteso corretto a mano a {rend_override_val*100:.1f}% "
                    f"(volatilità/correlazioni restano storiche).")

        nomi_leggibili = [TICKER_TO_NOME.get(t, t) for t in pi["tickers"]]
        df_asset = pd.DataFrame({
            "Nome": nomi_leggibili, "Ticker": pi["tickers"],
            "Peso (%)": (pesi * 100).round(1),
            "Rend. annuo storico (%)": (pi["rend_annuo_asset"] * 100).round(2),
            "Volatilità annua (%)": (pi["vol_annua_asset"] * 100).round(2),
        })
        st.dataframe(df_asset, use_container_width=True, hide_index=True)

        with st.expander("🔗 Matrice di correlazione (sui rendimenti mensili)"):
            df_corr = pd.DataFrame(pi["corr"], index=pi["tickers"], columns=pi["tickers"])
            st.dataframe(df_corr, use_container_width=True)

        st.caption("⚠️ Volatilità/correlazioni storiche sono stime ragionevoli; il "
                   "rendimento medio storico molto meno. Meglio correggerlo a mano.")
    st.divider()


# ---------------------------------------------------------------------------
# KPI + GRAFICO
# ---------------------------------------------------------------------------
st.subheader(f"📊 Andamento Capitale Netto — linea P{percentile_perf} · banda P10–P90")
st.caption("Linea = percentile scelto (carriera mediana). Banda = P10–P90 sulla "
           "variabilità dei RENDIMENTI ({} scenari).".format(N_BAND))

last = df_main.iloc[-1]
b_fondo = bande["Fondo Netto (€)"]
b_pac = bande["PAC Netto (€)"]
b_pactfr = bande["PAC + TFR Netto (€)"]
b_fpac = bande["Fondo + PAC Netto (€)"]

cols = st.columns(4 if usa_entrambi else 3)
cols[0].metric("Fondo Netto", f"€ {last['Fondo Netto (€)']:,.0f}",
               help=f"P10: € {b_fondo['p10'][-1]:,.0f} — P90: € {b_fondo['p90'][-1]:,.0f}")
cols[1].metric("PAC + TFR Netto", f"€ {last['PAC + TFR Netto (€)']:,.0f}",
               help=f"P10: € {b_pactfr['p10'][-1]:,.0f} — P90: € {b_pactfr['p90'][-1]:,.0f}")
cols[2].metric("RAL Finale", f"€ {last['RAL (€)']:,.0f}",
               help=f"× {last['RAL (€)']/ral:.2f} vs partenza" if ral else "")
if usa_entrambi:
    cols[3].metric("Fondo + PAC (senza TFR)", f"€ {last['Fondo + PAC Netto (€)']:,.0f}",
                   help=f"P10: € {b_fpac['p10'][-1]:,.0f} — P90: € {b_fpac['p90'][-1]:,.0f}")

fig = go.Figure()

def aggiungi_banda(b, colore_fill, nome):
    fig.add_trace(go.Scatter(
        x=anni + anni[::-1],
        y=list(b["p90"]) + list(b["p10"])[::-1],
        fill="toself", fillcolor=colore_fill,
        line=dict(color="rgba(0,0,0,0)"), name=nome, hoverinfo="skip",
        showlegend=True,
    ))

# Bande P10–P90 su tutte le curve principali
aggiungi_banda(b_fondo,  "rgba(42,120,214,0.12)", "Fondo P10–P90")
aggiungi_banda(b_pactfr, "rgba(27,175,122,0.12)", "PAC+TFR P10–P90")
aggiungi_banda(b_pac,    "rgba(155,89,182,0.10)", "Solo PAC P10–P90")
if usa_entrambi:
    aggiungi_banda(b_fpac, "rgba(237,161,0,0.10)", "Fondo+PAC P10–P90")

# Linee centrali (percentile scelto)
fig.add_trace(go.Scatter(x=anni, y=df_main["Fondo Netto (€)"], name="Fondo Pensione",
                         line=dict(color="#2a78d6", width=3)))
fig.add_trace(go.Scatter(x=anni, y=df_main["PAC + TFR Netto (€)"], name="PAC + TFR",
                         line=dict(color="#1baf7a", width=3)))
fig.add_trace(go.Scatter(x=anni, y=df_main["PAC Netto (€)"], name="Solo PAC",
                         line=dict(color="#9b59b6", width=2, dash="dash")))
if usa_entrambi:
    fig.add_trace(go.Scatter(x=anni, y=df_main["Fondo + PAC Netto (€)"],
                             name="Fondo + PAC (senza TFR)",
                             line=dict(color="#eda100", width=3, dash="dot")))

fig.update_layout(xaxis_title="Anno", yaxis_title="Capitale Netto (€)",
                  yaxis_tickformat="€,.0f", hovermode="x unified",
                  legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                  height=460)
st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# TABELLA ANNO PER ANNO
# ---------------------------------------------------------------------------
st.subheader("📋 Dettaglio Anno per Anno")
st.caption("Montanti = linea centrale P{}. Contributi e RAL crescono con carriera/inflazione.".format(percentile_perf))

cols_show = ["Anno", "CCNL", "Livello", "Comparto", "Scatti", "Occupato", "RAL (€)",
             "Contrib. Min. CCNL (€)", "Vers. Volontario (€)", "TFR al Fondo (€)",
             "Contrib. Aziendale (€)", "Risparmio IRPEF (€)", "PAC annuo (€)",
             "Aliq. uscita fondo (%)", "Fondo Netto (€)", "PAC + TFR Netto (€)", "PAC Netto (€)"]
if usa_entrambi:
    cols_show.append("Fondo + PAC Netto (€)")

fmt = {c: "€ {:,.0f}" for c in cols_show
       if c not in ("Anno", "CCNL", "Livello", "Comparto", "Scatti", "Occupato", "Aliq. uscita fondo (%)")}
fmt["Aliq. uscita fondo (%)"] = "{:.1f}%"
st.dataframe(df_main[cols_show].style.format(fmt), use_container_width=True, height=420)

st.caption(
    "⚠️ Stima illustrativa. Crescita salariale su dati ISTAT; contributi CCNL "
    "Cometa/Fon.Te; costi/comparti da schede COVIP; rendimenti simulati con GBM o "
    "bootstrap storico. La banda P10–P90 riflette l'incertezza dei rendimenti, non "
    "quella di carriera. Non è consulenza finanziaria o previdenziale."
)
