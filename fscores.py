import settings
from django.core.management import setup_environ
setup_environ(settings)

from collections import defaultdict
from datetime import datetime, timedelta
import gc
from django.db.models import F
from dashboard.models import *

def get_village_list(params):
    village_qs = Village.objects.filter(id__in=params['village_ids']).filter(block__block_name=params['block_name'])
    village_list = village_qs.values_list('id', flat=True)
    return village_list

def get_person_list(params, village_list):
    person_list = Person.objects.filter(village__in=village_list).filter(group__isnull=False)
    # For data integrity sake we are checking if the block in which the village is, is the same as the block in which the group is. There are occassions where this is not the case. People in such a group have not been considered.
    # If we don't do this, then our distance calculations go berserk
    person_list = person_list.filter(village=F('group__village'))
    return person_list

def compute_group_distance_matrix(log, params, village_list):
    distance = defaultdict(dict)
    all_groups = PersonGroups.objects.select_related('village').filter(village__in=village_list).all()
    log.write(str(len(all_groups)))
    try:
        for group1 in all_groups:
            for group2 in all_groups:
                try:     
                    if group1 == group2:
                        distance[group1.id][group2.id] = params['distance']['same_group']
                    elif group1.village == group2.village:
                        distance[group1.id][group2.id] = params['distance']['same_village']
                    else:
                        distance[group1.id][group2.id] = params['distance']['same_block']
                except:
                    log.write("Error in function: compute_group_distance_matrix %s %s." % (group1.id, group2.id))
                    continue
    except:
        log.write("something crashed")
    return distance

# Dictionary indexed by person, and then by video with value date_of_screening
def compute_viewing_stats(params, person_list, video_list):
    # compute scr_list - list of person_id, video_id, date
    col_video = 'personmeetingattendance__screening__videoes_screened'
    col_date = 'personmeetingattendance__screening__date'
    # Filtering pmas by person_list and video_list
    
    scr_list = person_list.filter(**{col_video+'__in':video_list}).values_list('id', col_video, col_date)
    scr_date = defaultdict(dict)
    number_of_viewers = {
        'group': defaultdict(lambda: defaultdict(lambda: 0)),
        'village': defaultdict(lambda: defaultdict(lambda: 0)),
        'block': defaultdict(lambda: defaultdict(lambda: 0)),
    }
    for person_id, video_id, date in scr_list:
        if not scr_date[person_id].has_key(video_id):
            scr_date[person_id][video_id] = date
            # one person has seen this video, so let's also increase viewership counts
            person = Person.objects.select_related("group__id", "village__id", "village__block__id").get(id=person_id)
            number_of_viewers['group'][person.group.id][video_id] += 1
            number_of_viewers['village'][person.village.id][video_id] += 1
            number_of_viewers['block'][person.village.block.id][video_id] += 1
        elif scr_date[person_id][video_id] > date:
            # second instance viewing of the same video
            # first viewing date
            scr_date[person_id][video_id] = date
    return {
        'screening_date': scr_date,
        'number_of_viewers': number_of_viewers,
    }

# Dictionary indexed by video, and then by person with value date_of_adoption
def compute_adoption_stats(params, person_list, video_list):
    adoption_list = PersonAdoptPractice.objects.filter(person__in=person_list).filter(video__in=video_list).values('person','video', 'date_of_adoption')
    adoption_date = defaultdict(dict)
    number_of_videos_adopted = defaultdict(lambda: 0)
    for row in adoption_list:
        if not adoption_date[row['video']].has_key(row['person']):
            adoption_date[row['video']][row['person']] = row['date_of_adoption']
            number_of_videos_adopted[row['person']] += 1
        elif adoption_date[row['video']][row['person']] > row['date_of_adoption']:
            # Date of first adoption
            adoption_date[row['video']][row['person']] = row['date_of_adoption']
    return {
        'adoption_date': adoption_date,
        'adoption_counts': number_of_videos_adopted,
    }

def get_confused(params, person, adoption_date, video_seen_list, viewership_counts, group_distance):
    distance = params['distance']
    person_obj = Person.objects.get(id=person)
    confusion = {
        'tp' : 0,
        'fp' : 0,
        'tn' : 0,
        'fn' : 0,
    }
    for video, scr_date in video_seen_list.iteritems():
        # check adoptions of this video for all other people
        if adoption_date.has_key(video):
            # Compute the highest possible True or False Positive value attainable, attainable if every person who has seen that video
            viewers_in_group = viewership_counts['group'][person_obj.group.id][video]
            viewers_in_village = viewership_counts['village'][person_obj.village.id][video]
            viewers_in_block = viewership_counts['block'][person_obj.village.block.id][video]
            highest_possible_tp_fn = (viewers_in_group - 1)/distance['same_group'] + (viewers_in_village - viewers_in_group)/distance['same_village'] + (viewers_in_block - viewers_in_village)/distance['same_block']
            ### Definitions
            # true positives (actual influenced adopters that were correctly classified as influenced adopters)	
            # false negatives (actual influenced adopters that were incorrectly marked as or pre-adopters, non-adopters)
            # false positives (pre-adopters, non-adopters that were incorrectly labeled as adopters)	
            # true negatives (all the remaining classes, correctly classified as non-influenced-adopters)
            ###
            if adoption_date[video].has_key(person): 
                # person has adopted
                window_date = adoption_date[video][person] + timedelta(days = params['window'])
                tmp_tp = 0
                for p, date_of_adoption in adoption_date[video].iteritems():
                    p_obj = Person.objects.get(id=p)
                    if date_of_adoption >= window_date:
                        tmp_tp = tmp_tp + 1.0/group_distance[person_obj.group.id][p_obj.group.id]
                confusion['tp'] = confusion['tp'] + tmp_tp
                confusion['fp'] = confusion['fp'] + highest_possible_tp_fn - tmp_tp
            else:
                tmp_fn = 0
                for p, date_of_adoption in adoption_date[video].iteritems():
                    p_obj = Person.objects.get(id=p)
                    if date_of_adoption > scr_date:
                        tmp_fn = tmp_fn + 1.0/group_distance[person_obj.group.id][p_obj.group.id]
                confusion['fn'] = confusion['fn'] + tmp_fn
                confusion['tn'] = confusion['tn'] + highest_possible_tp_fn - tmp_fn
    return confusion
    
def compute_fscores():
    # crop
    # time period
    # distance
    # window
    print 'person_id, fscore, tp, tn, fn, fp, num_videos_seen, num_videos_adopted'
    log = open('logfile.txt', 'a')
    log.write(str(datetime.now()))
    gc.enable()
    params = {
        'block_name': 'ghatagaon',
        'distance': {
            'same_group': 1,
            'same_village': 4,
            'same_block' : 16,
        },
        'window': 7,
        'village_ids': [10000000019978,10000000019979,10000000019980,10000000019981,10000000019982,10000000019983,10000000019984,10000000019985,10000000019986,10000000019987,10000000019988,10000000019989,10000000019990,10000000019991,10000000019992,10000000019993,10000000019994,10000000019995,10000000019996,10000000019997,10000000020104,10000000020105,10000000020106,10000000020107,10000000020108,10000000020119,10000000020120,10000000020132,10000000020133,10000000020134,10000000020369,10000000020370,10000000020589,10000000020590,10000000020591,10000000020592,10000000020595,10000000020596,10000000020600,10000000020601,10000000020602,10000000020603,10000000020604,10000000020605,10000000020606,10000000020607,10000000020608,10000000020610,10000000020611,10000000020612,10000000020613,10000000020615,10000000020754],
    }
    village_list = get_village_list(params)
    person_list = get_person_list(params, village_list)
    group_distance = compute_group_distance_matrix(log, params, village_list)
    video_list = Video.objects.filter(village__block__district__district_name='keonjhar')
    stats = compute_viewing_stats(params, person_list, video_list)
    screening_date = stats['screening_date']
    viewership_counts = stats['number_of_viewers']
    adoption_stats = compute_adoption_stats(params, person_list, video_list)
    adoption_date = adoption_stats['adoption_date']
    fscore = {}
    log.write(str(datetime.now()))
    for person, video_seen_list in screening_date.iteritems():
        confusion = get_confused(params, person, adoption_date, video_seen_list, viewership_counts, group_distance)
        gc.collect()
        try:
            fscore[person] = 2.0*confusion['tp']/(2*confusion['tp'] + confusion['fn'] + confusion['fp'])
        except ZeroDivisionError:
            fscore[person] = 0
        result = [person, fscore[person], confusion['tp'], confusion['tn'], confusion['fn'], confusion['fp']]
        result.extend([len(video_seen_list), adoption_stats['adoption_counts'][person]]) 
        print ','.join([str(x) for x in result])
    log.write(str(datetime.now()))
    log.close()

compute_fscores()
