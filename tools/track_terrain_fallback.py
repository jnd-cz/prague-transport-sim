"""Last no-data proposal for #20: ordinary track's IPR terrain plus the approved drawing offset."""
from track_heights import usable


def ordinary_fallback(row, ground_z, facts):
    flags = row['review_flags']
    if (row['status']!='review' or 'no_usable_height' not in flags or not usable(ground_z)
            or any(f in flags for f in ('structure_hint','structure_unverified','tunnel_unverified',
                                        'track_zps_level_unverified','known_archive_disagreement'))):
        return None
    styles = set(row.get('construction',{}).get('styles',[])) or {'panels'}
    x,y = row['xy']
    applicable = [f for f in facts if (not f.get('styles') or styles.intersection(f['styles']))
                  and (f.get('scope')=='all' or str(row['di_id']) in {str(i) for i in f.get('di_ids',[])}
                       or f.get('bounds') and f['bounds'][0]<=x<=f['bounds'][2] and f['bounds'][1]<=y<=f['bounds'][3])]
    if not applicable or len({f['metres'] for f in applicable})!=1:
        return None
    offset = applicable[0]['metres']
    return {'z':round(ground_z+offset,3),'terrain_z':round(ground_z,3),'offset_m':offset,
            'offset_fact_ids':[f['id'] for f in applicable], 'track_styles':sorted(styles),
            'height_source':{'dataset':'ipr-dtm','record':'raw/ipr-dtm/DTM/dtm_1m.tif',
                             'resolution_m':1,'observation_year':2023,'processed_date':'2025-07-10',
                             'datum':'Bpv_assumed'},
            'confidence':'ordinary_terrain_approximation','review_flags':['terrain_fallback_unvalidated'],
            'scope':'Proposal for #20 profile assembly; no structure or world geometry is changed.'}
