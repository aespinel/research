import settings
from django.core.management import setup_environ
setup_environ(settings)
import gc
from dashboard.models import *
from django.db.models import Count, F, Q
import datetime
#import xlwt
import pickle
from datetime import timedelta
print datetime.datetime.now()
gc.enable()
study_block_name = 'keonjhar'
block = block = Block.objects.get(block_name=study_block_name)
person_list = Person.objects.filter(village__block=block).filter(group__isnull=False).filter(village__block=F('group__village__block'))
print len(person_list)

# compute scr_list - list of person_id, video_id, date
scr_list = person_list.values_list('id','personmeetingattendance__screening__videoes_screened','personmeetingattendance__screening__date')
# compute scr_date - dictionary indexed by video, and then by person with value date_of_screening
scr_date = {}
for person_id, video_id, date in scr_list:
    if not scr_date.has_key(person_id):
        scr_date[person_id] = {}
    if not scr_date[person_id].has_key(video_id):
        scr_date[person_id][video_id] = date
    else:
        if scr_date[person_id][video_id] > date:
                scr_date[person_id][video_id] = date


# compute adopter_ids, dictionary indexed by person with (person_id, video_id, date_of_adoption)
adopter_ids = person_list.values_list('id', flat=True)
adoption_list = []
for id in adopter_ids:
    row = PersonAdoptPractice.objects.filter(person=id).values('person','video', 'date_of_adoption')
    adoption_list.extend(row)

# compute adoption_date, dictionary indexed by video, and then by person with value date_of_adoption
adoption_date = {}
for row in adoption_list:
    if not adoption_date.has_key(row['video']):
        adoption_date[row['video']] = {}
    if not adoption_date[row['video']].has_key(row['person']):
        adoption_date[row['video']][row['person']] = row['date_of_adoption']
    else:
        if adoption_date[row['video']][row['person']] > row['date_of_adoption']:
            adoption_date[row['video']][row['person']] = row['date_of_adoption']

##############DUMPING VALUES###################################
fp = open('data','wb')
pickle.dump({
    'screening_date': scr_date,
    'adoption_date': adoption_date,
},fp)
fp.close()

fp = open('data','rb')
loaded = pickle.load(fp)
fp.close()
###############################################################
screening_date = loaded['screening_date']
adoption_date = loaded['adoption_date']

fscore = {}

from dashboard.models import *
import pickle

# compute video_count - how many people have seen a video in a group
new_video_group_count = {}
for video in adoption_date.keys():
    new_video_group_count[video] = {}
    for group in PersonGroups.objects.filter(village__block=block):
        new_video_group_count[video][group.id] = person_list.filter(group = group, personmeetingattendance__screening__videoes_screened=video).count()

# compute video_count - how many people have seen a video in a village, block
new_video_village_count = {}
new_video_block_count = {}
for video in adoption_date.keys():
    new_video_village_count[video] = {}
    new_video_block_count[video] = 0
    for village in Village.objects.filter(block=block):
        new_video_village_count[video][village.id] = person_list.filter(village = village, personmeetingattendance__screening__videoes_screened=video).count()
        new_video_block_count[video] = new_video_block_count[video] + new_video_village_count[video][village.id]

group_dist = {}  
for v1 in PersonGroups.objects.filter(village__block__block_name=study_block_name):
    group_dist[v1.id] = {}
    for v2 in PersonGroups.objects.filter(village__block__block_name=study_block_name):
        try:
            if v1 == v2:
                group_dist[v1.id][v2.id] = 1
            elif v1.village == v2.village:
                group_dist[v1.id][v2.id] = 4
            else:
                group_dist[v1.id][v2.id] = 16
        except:
            print "ERROR"
            continue

def get_confused(person):
    person_obj = Person.objects.get(id=person)
    confusion = {
        'tp' : 0,
        'fp' : 0,
        'tn' : 0,
        'fn' : 0,
        }
    for video, scr_date in video_seen_list.iteritems():
        if adoption_date.has_key(video):
            num_people_group = new_video_group_count[video][person_obj.group.id]
            num_people_village = new_video_village_count[video][person_obj.village.id]
            num_people_block = new_video_block_count[video]
            total_num_people = num_people_group + (num_people_village - num_people_group)/4 + (num_people_block - num_people_village)/16
            if adoption_date[video].has_key(person): 
                # person has adopted
                date = adoption_date[video][person]
                tmp_tp = 0
                for p, date_of_adoption in adoption_date[video].iteritems():
                    p_obj = Person.objects.get(id=p)
                    one_week_date = date_of_adoption + timedelta(days = 7)
                    if one_week_date >= date:
                        dist = group_dist[person_obj.group.id][p_obj.group.id]
                        tmp_tp = tmp_tp + 1.0/dist
                confusion['tp'] = confusion['tp'] + tmp_tp
                confusion['fp'] = confusion['fp'] + total_num_people - tmp_tp - 1
            else:
                date = scr_date
                tmp = 0
                for p, date_of_adoption in adoption_date[video].iteritems():
                    p_obj = Person.objects.get(id=p)
                    if date_of_adoption > date:
                        dist = group_dist[person_obj.group.id][p_obj.group.id]
                        tmp = tmp + 1.0/dist
                confusion['fn'] = confusion['fn'] + tmp
                confusion['tn'] = confusion['tn'] + total_num_people - tmp - 1
    return confusion

for person, video_seen_list in screening_date.iteritems():
    confusion = get_confused(person)
    gc.collect()
    try:
        fscore[person] = 2.0*confusion['tp']/(2*confusion['tp'] + confusion['fn'] + confusion['fp'])
        print str(person) + " " + str(fscore[person])
    except ZeroDivisionError:
        fscore[person] = 0
print datetime.datetime.now()
      
fp = open('keonjhar','wb')
pickle.dump({
    'fscore': fscore,
},fp)
fp.close()

