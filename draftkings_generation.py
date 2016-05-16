#!/usr/bin/env python3
import time
import pandas as pd

from ortools.linear_solver import pywraplp
from flask import Flask
from flask import request
from flask import send_from_directory
from flask import jsonify

from two1.wallet import Wallet
from two1.bitserv.flask import Payment

SALARY_CAP = 50000
ROSTER_SIZE =8 
POSITIONS = [
    ["PG", 1, 3],
    ["SG", 1, 3],
    ["SF", 1, 3],
    ["PF", 1, 3],
    ["C", 1, 2]
  ]

class Player:
    def __init__(self, pos, name, cost, 
                 matchup=None, team=None, stage=None, proj=0, marked=None):
        self.pos = pos
        self.name = name
        self.cost = int(cost)
        self.team =  team
        self.matchup = matchup
        self.proj = proj
        self.marked = marked
        self.stage = stage

    def serialize(self):
        return {
            'Position': self.pos, 
            'Name': self.name,
            'Team': self.team,
            'Matchup': self.matchup,
            'Cost': self.cost,
            'Proj': self.proj,
            'Stage': self.stage
        }

class Roster:
    def __init__(self):
        self.players = []
    def add_player(self, player):
        self.players.append(player)

    def spent(self):
        return sum(map(lambda x: x.cost, self.players))

    def projected(self):
        return sum(map(lambda x: x.proj, self.players))

    def position_order(self, player):
        return self.POSITION_ORDER[player.pos]

    def sorted_players(self):
        return sorted(self.players, key=self.position_order)

    def __repr__(self):
        s = '\n'.join(str(x) for x in self.sorted_players())
        s += "\n\nProjected Score: %s" % self.projected()
        s += "\tCost: $%s" % self.spent()
        return s

class NBARoster(Roster):
    POSITION_ORDER = {
        "PG": 0,
        "SG": 1,
        "SF": 2,
        "PF": 3,
        "C": 4
    }

    def roster_gen(self):
        roster_dict = {
            'NBA' : NBARoster()
            }
        return roster_dict[self]

    def list_players(self):
        player_list = [player for player in self.players]
        return player_list    

    def calculate_roster_total(self):
        players = self.list_players()
        serialized = [x.serialize() for x in players]
        total_cost = sum([player['Cost'] for player in serialized])
        total_proj = sum([player['Proj'] for player in serialized])
        return([{'Projected Score': total_proj, 'Total Cost': total_cost}])


def run_solver(solver, all_players, position_distribution):
    '''
    Set objective and constraints, then optimize
    '''
    variables = []

    for player in all_players:
        variables.append(solver.IntVar(0, 1, player.name))
      
    objective = solver.Objective()
    objective.SetMaximization()

    # optimize on projected points
    for i, player in enumerate(all_players):
        objective.SetCoefficient(variables[i], player.proj)

    # set salary cap constraint
    salary_cap = solver.Constraint(0, SALARY_CAP)
    for i, player in enumerate(all_players):
        salary_cap.SetCoefficient(variables[i], player.cost)

    # set roster size constraint
    size_cap = solver.Constraint(ROSTER_SIZE, 
                                 ROSTER_SIZE)
    for variable in variables:
        size_cap.SetCoefficient(variable, 1)

    # set position limit constraint
    for position, min_limit, max_limit in POSITIONS:
        position_cap = solver.Constraint(min_limit, max_limit)

        for i, player in enumerate(all_players):
            if position == player.pos:
                position_cap.SetCoefficient(variables[i], 1)

    return variables, solver.Solve()




app = Flask(__name__)
app.debug=True
payment = Payment(app, Wallet())

@app.route('/draftkings')
@payment.required(1000)
def draftkings():
    position_distribution = POSITIONS
    solver = pywraplp.Solver('FD', 
                             pywraplp.Solver.CBC_MIXED_INTEGER_PROGRAMMING)
    all_players = []
    csv_data = pd.read_csv('csv_data/DKSalaries.csv').to_dict("records")

    for row in csv_data:
        team = row['teamAbbrev']
        unparsed_matchup = row['GameInfo']
        parsed_matchup =unparsed_matchup.split("@")
        if team == parsed_matchup[0]:
            stage = 'HOME'
            matchup = parsed_matchup[1].split(" ")[0]
        else:
            stage ='AWAY'
            matchup = parsed_matchup[0]
        current_player = Player(
            row['Position'],
            row['Name'],
            row['Salary'], 
            matchup=matchup.upper(),
            team=team.upper(),
            stage=stage,
            proj=row['AvgPointsPerGame'])
        all_players.append(current_player)

    variables, solution = run_solver(solver, 
                                     all_players, 
                                     position_distribution)

    if solution == solver.OPTIMAL:
        roster = NBARoster.roster_gen("NBA")

        for i, player in enumerate(all_players):
            if variables[i].solution_value() == 1:
                roster.add_player(player)

        players = roster.list_players()
        dicted_players = [x.serialize() for x in players]
        roster_stats = roster.calculate_roster_total()
        return(jsonify({'Roster Statistics':roster_stats, 'Roster':dicted_players}))


if __name__ == "__main__":
    #run_draftkings()
    app.run(host="0.0.0.0", port=5000)



