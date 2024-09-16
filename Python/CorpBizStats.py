import pandas as pd
from bs4 import BeautifulSoup
import requests as r
import numpy as np
import datetime as dt
import time
from fake_useragent import UserAgent

ua = UserAgent()

# Get current season
current_season = dt.date.today().year

# Specify base URL
url = 'https://statsapi.mlb.com/api/v1/'

# Set the schedule URL
schedule_url = url + ('schedule/?sportId=1&season=%s&gameTypes=R&teamId=136' % current_season)

# Get the schedule for this season
test = r.get(schedule_url, headers={'user-agent': ua.random})

# Convert schedule to JSON
test_json = test.json()

# Function to merge 3 dictionaries
def merge3(dict1, dict2, dict3):
    res = {**dict1, **dict2, **dict3}
    return res

# Function to get date and time
def get_date(date):
    format = '%Y-%m-%dT%H:%M:%SZ'
    date = dt.datetime.strptime(date, format) - dt.timedelta(hours=7)
    date_split = date.strftime(format).split('T')
    return [date_split[0], '19:10' if (date_split[0] == '2022-10-04') and (date_split[1][:5] == '15:15:00') else date_split[1][:8]]

# Function to get the basic game stats of the game
def extract_bs_stats(game_pk, home_team):
    boxscore_url = url + 'game/%s/boxscore' % game_pk
    response = r.get(boxscore_url, headers={'user-agent': ua.random})
    boxscore = response.json()

    sea = None
    opp = None
    
    if home_team == 136:
        sea = 'home'
        opp = 'away'
    else:
        sea = 'away'
        opp = 'home'

    sea_boxscore = boxscore['teams'][sea]['teamStats']
    opp_boxscore = boxscore['teams'][opp]['teamStats']

    result = {}

    # result['Game_Pk'] = game_pk
    result['Home_Runs'] = sea_boxscore['batting']['homeRuns']    
    result['Seven_Or_More_Runs'] = (sea_boxscore['batting']['runs'] >= 7)*1 
    result['Five_Or_More_Runs'] = (sea_boxscore['batting']['runs'] >= 5)*1
    result['Three_Or_More_Runs'] = (sea_boxscore['batting']['runs'] >= 3)*1
    result['Triples'] = sea_boxscore['batting']['triples']
    result['Runs'] = sea_boxscore['batting']['runs']
    result['Bunts'] = sea_boxscore['batting']['sacBunts']
    result['Stolen_Bases'] = sea_boxscore['batting']['stolenBases']
    result['Doubles'] = sea_boxscore['batting']['doubles']
    result['Double_Plays'] = opp_boxscore['batting']['groundIntoDoublePlay']
    result['Caught_Stealing'] = opp_boxscore['batting']['caughtStealing']
    result['Pitcher_Pickoff'] = sea_boxscore['pitching']['pickoffs']
    result['Hits'] = sea_boxscore['batting']['hits']
    result['Walks'] = sea_boxscore['batting']['baseOnBalls']
    result['Strikeouts'] = sea_boxscore['pitching']['strikeOuts']
    result['Runs_Batted_In'] = sea_boxscore['batting']['rbi']
    result['Assists'] = sea_boxscore['fielding']['assists']

    return result

# Extract stats that require looking at the play-by-play data
def extract_pbp_stats(game_pk, home_team):
    pbp_url = url + 'game/%s/playByPlay' % game_pk
    response = r.get(pbp_url, headers={'user-agent': ua.random})
    pbp = response.json()
    
    sea_home = home_team == 136

    replay_review = 0
    strike_out_side = 0
    four_pitch_walk = 0
    
    pitches_by_inning = {}
    batting_by_inning = {}

    length = dt.datetime.strptime(pbp['allPlays'][-1]['about']['endTime'] , '%Y-%m-%dT%H:%M:%S.%fZ') - dt.datetime.strptime(pbp['allPlays'][0]['about']['startTime'] , '%Y-%m-%dT%H:%M:%S.%fZ')

    length_hours = round(length.total_seconds() / (60 * 60), 2)

    for play in pbp['allPlays']:
        inning = play['about']['inning']
        inning_half = play['about']['isTopInning']

        if sea_home:
            if inning_half:
                if inning in pitches_by_inning.keys():
                    pitches_by_inning[inning].append(play['result'])
                else:
                    pitches_by_inning[inning] = []
                    pitches_by_inning[inning].append(play['result'])
            else:
                if inning in batting_by_inning.keys():
                    batting_by_inning[inning].append(merge3(play['result'], play['count'], play['about']))
                else:
                    batting_by_inning[inning] = []
                    batting_by_inning[inning].append(merge3(play['result'], play['count'], play['about']))
        else:
            if inning_half:
                if inning in batting_by_inning.keys():
                    batting_by_inning[inning].append(merge3(play['result'], play['count'], play['about']))
                else:
                    batting_by_inning[inning] = []
                    batting_by_inning[inning].append(merge3(play['result'], play['count'], play['about']))
            else:
                if inning in pitches_by_inning.keys():
                    pitches_by_inning[inning].append(play['result'])
                else:
                    pitches_by_inning[inning] = []
                    pitches_by_inning[inning].append(play['result'])

    for inning in pitches_by_inning.keys():
        if len(pitches_by_inning[inning]) == 3:
            num_so = 0
            for i in range(0, 3):
                if pitches_by_inning[inning][i]['eventType'] == 'strikeout':
                    num_so += 1
            if num_so == 3:
                strike_out_side += 1

    for inning in batting_by_inning.keys():
        for play in batting_by_inning[inning]:
            replay_review += play['hasReview']*1
            four_pitch_walk += ((play['eventType'] == 'walk') & (play['balls'] == 4) & (play['strikes'] == 0))*1

    return {'Replay_Reviews': replay_review, 'Four_Pitch_Walk': four_pitch_walk, 'Strikeout_Side': strike_out_side, 'Length': length_hours}

result = []

# Loop through each game in the schedule and create the dataset
for date in test_json['dates']:
    for game in date['games']:
        if (game['status']['abstractGameState'] == 'Final') and (game['status']['detailedState'] != 'Postponed') and (dt.datetime.strptime(game['officialDate'], '%Y-%m-%d') >= dt.datetime.strptime('2022-04-08', '%Y-%m-%d')):
            game_pk = game['gamePk']
            home_team = game['teams']['home']['team']['id']
            win = None
            if home_team == 136:
                win = game['teams']['home']['isWinner']*1
            else:
                win = game['teams']['away']['isWinner']*1
            date_info = get_date(game['gameDate'])
            result.append(merge3(extract_bs_stats(game_pk, home_team), extract_pbp_stats(game_pk, home_team), {'Wins': win, 'Game_Date': str(date_info[0]), 'Game_Time': str(date_info[1])}))
            time.sleep(0.5)

# Conver the list of objects to a pandas dataframe
result = pd.DataFrame(result)

# Set the order of the columns
cols = [
    'Game_Date',
    'Game_Time',
    'Length',        
    'Home_Runs', 
    'Wins',
    'Replay_Reviews', 
    'Strikeout_Side', 
    'Four_Pitch_Walk', 
    'Triples', 
    'Seven_Or_More_Runs', 
    'Five_Or_More_Runs', 
    'Three_Or_More_Runs',
    'Bunts',
    'Stolen_Bases',
    'Doubles',
    'Double_Plays',
    'Save',
    'Caught_Stealing',
    'Pitcher_Pickoff',
    'Hits',
    'Runs',
    'Walks',
    'Strikeouts',
    'Runs_Batted_In',
    'Assists'
    ]

# Obtaining save data from baseball reference
saves = []
scheduleURL = r.get("https://www.baseball-reference.com/teams/SEA/%s-schedule-scores.shtml" % current_season, headers={'user-agent': ua.random})
scheduleSoup = BeautifulSoup(scheduleURL.content, 'html.parser')
scheduleTable = pd.read_html(str(scheduleSoup.find_all("table")))[0]
scheduleTable = scheduleTable[(scheduleTable["Unnamed: 2"] == "boxscore")]
scheduleTable["Save_Track"] = np.where((scheduleTable['W/L'] == "W") & (scheduleTable["Save"].notnull()), 1,0)
scheduleTable["Extra_Innings"] = np.where(scheduleTable["Inn"].fillna('-1').astype(int) > 9,1,0)

saves = saves + scheduleTable["Save_Track"].tolist()

# Set the saves to the result
result['Save'] = saves

# print(result)
# result[cols].to_csv("C:\\Users\\ksarausad\\OneDrive - SODO Labs\\Desktop\\projects\\Stat Scrape\\Runs\\Corporate-Business-Stats " + dt.datetime.today().strftime("%m%d%Y") + '.csv', index=False)
# result[cols].to_csv("\\\\clemente\\TicketSales\\Reports\\2024 Season\\SSRS Reports\\Corporate-Business-Stats.csv", index=False)
result[cols].to_csv("Data/Corporate-Business-Stats " + dt.datetime.today().strftime("%m%d%Y") + '.csv', index=False)
