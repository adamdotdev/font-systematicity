from  datetime import datetime
import io
import json
import math
import random
from enum import Enum

import data
from data import Font, Experiment, ExperimentGlyphSet
import shapes
import systematicity

class ExperimentType(Enum):
    DefaultSystematicity = "default"
    GridSearch = "grid"
    RandomSearch = "random"
    SimulatedAnnealing = "simulated annealing",
    SimulatedAnnealingMin = "simulated annealing minimize"


random_seed = None

"""
    Method for setting initial seed for when repeatable experiments
    are desired.
"""
def set_random_seed(seed):
    random_seed = seed

"""
    Evaluate the systematicity in sound-shape correlation for a set of fonts
    and font sizes. For variable fonts, evalutes default coordinate values
    only.
"""
def evaluate_fonts(chars, fonts, font_sizes):
    for font in fonts:
        for font_size in font_sizes:
            systematicity.evaluate(chars, font, font_size, None)

"""
    Generates a set number of evenly spaced points in the specified space.
"""
def get_grid_coords(minimum, maximum, points):
    if points < 2:
        raise Exception("Points must be greater than or equal to 2")
    if minimum > maximum:
        raise Exception("Minimum must be less than or equal maximum")
        
    interval = (maximum - minimum) / (points - 1)
    return [round(interval * i + minimum, 4) for i in range(points)]

"""
    Generates the number of randomly selected points for the specified
    font axes.
"""
def get_random_coords(axes, num_points):
    points = []
    for i in range(num_points):
        coords = []
        for axis in axes:
            coords.append(round(random.uniform(axis.minimum, axis.maximum), 4))
        points.append(coords)
    return points

"""
    Get best systematiciy performing a grid search over the possible values of
    each individual axis. Modifies only a single axis at a time: all other axes
    are set to their default values.
"""
def grid_search(chars, fonts, font_sizes, grid_count):
    for font in fonts:
        for font_size in font_sizes:
            experiment_name = "Grid: {0} size {1}, {2} facets.".format(font.name, font_size, grid_count)
            experiment = Experiment(
                name = experiment_name,
                method = ExperimentType.GridSearch,
                start_time = datetime.now(),
                hyperparameters = json.dumps({"facets":grid_count}))
            experiment.save()
            print(experiment_name)

            random.seed(random_seed)
        
            renderer = shapes.GlyphRenderer(io.BytesIO(font.font_file))
            defaults = [axis.default for axis in renderer._axes]
            best_corr = 0.0

            for index in range(len(renderer._axes)):
                axis = renderer._axes[index]
                vals = get_grid_coords(axis.minimum, axis.maximum, grid_count)
                best_axis_corr = 0.0

                for idx, val in enumerate(vals):
                    coords = defaults.copy()
                    coords[index] = val
                    
                    try:
                        result = systematicity.evaluate(chars, font, font_size, coords)
                    except systematicity.FailedRenderException:
                        # ignore failed render and carry on
                        print("Failed render at point {0}".format(coords))
                        continue

                    save_result(experiment.id, result)
                    
                    print("Corr {0:.4f} for {1} pt {2} for {3} value of {4}".format(result.edit_correlation, font_size, font.name, axis.name, val))
                    if result.edit_correlation > best_axis_corr:
                        best_axis_corr = result.edit_correlation
                    if result.edit_correlation > best_corr:
                        best_corr = result.edit_correlation
            
                print("Best corr: {0:.4f} for axis {1}".format(best_axis_corr, axis.name))
            
            print("Best corr: {0:.4f}".format(best_corr))
            experiment.end_time = datetime.now()
            experiment.save()

"""
    Perform a random search over the possible values of each font's axes.
    Generates num_points candidates.
"""
def random_search(chars, fonts, font_sizes, num_points):
    for font in fonts:
        for font_size in font_sizes:
            experiment_name = "Random: {0} size {1}, {2} points.".format(font.name, font_size, num_points)
            experiment = Experiment(
                name = experiment_name,
                method = ExperimentType.RandomSearch,
                start_time = datetime.now(),
                hyperparameters = json.dumps({"points":num_points}))
            experiment.save()
            print(experiment_name)

            random.seed(random_seed)

            renderer = shapes.GlyphRenderer(io.BytesIO(font.font_file))

            points = get_random_coords(renderer._axes, num_points)
            # Include min and max
            points.insert(0, [axis.minimum for axis in renderer._axes])
            points.append([axis.maximum for axis in renderer._axes])

            best_corr = 0.0

            iteration = 1
            for point in points:
                try:
                    result = systematicity.evaluate(chars, font, font_size, point)
                except systematicity.FailedRenderException:
                        # ignore failed render and carry on to next point
                        print("{0} Failed render at point {1}".format(iteration, point))
                        continue
                save_result(experiment.id, result)

                print("{0} Corr: {1:.4f} for {2} pt {3} with coords {4}...".format(
                    iteration, result.edit_correlation, font_size, font.name, point))
                if result.edit_correlation > best_corr:
                    best_corr = result.edit_correlation

                iteration += 1
            print("Best corr: {0:.4f}".format(best_corr))

            experiment.end_time = datetime.now()
            experiment.save()

"""
   Simulated annealing algorithm for finding optimal coordinates. 
"""
def simulated_annealing(chars, fonts, font_sizes, init_temp, time, alter_type="gaussian", alter_range="0.1", method=ExperimentType.SimulatedAnnealing):
    if method not in [ExperimentType.SimulatedAnnealing, ExperimentType.SimulatedAnnealingMin]:
        raise("Method must be one of the simulated annealing types")

    for font in fonts:
        for font_size in font_sizes:
            experiment_name = "Simulated Annealing: {0} size {1}, initial temp {2}, {3} iterations.".format(font.name, font_size, init_temp, time)
            experiment = Experiment(
                name = experiment_name,
                method = method,
                start_time = datetime.now(),
                hyperparameters = json.dumps({"temp":init_temp, "iterations":time, "alteration_type":alter_type, "alteration_range":alter_range}))
            experiment.save()
            
            random.seed(random_seed)

            print(experiment_name)
            temperature = init_temp
            renderer = shapes.GlyphRenderer(io.BytesIO(font.font_file))
            #candidate = get_random_coords(renderer._axes, 1)[0]
            candidate = [axis.default for axis in renderer._axes]
            
            result = systematicity.evaluate(chars, font, font_size, candidate)
            save_result(experiment.id, result)
            corr = result.edit_correlation
            
            iteration = 1
            
            best_candidate = candidate
            best_corr = corr
            best_iteration = iteration

            print("Starting at {0}, {1}".format(best_candidate, best_corr))

            while iteration < time and temperature > 0:
                if alter_type == "gaussian":
                    new_candidate = alter_gaussian(candidate, renderer._axes, alter_range)
                else:
                    new_candidate = alter_uniform(candidate, renderer._axes, alter_range)
                
                try:
                    result = systematicity.evaluate(chars, font, font_size, new_candidate)
                except systematicity.FailedRenderException:
                    # ignore failed render and carry on to a new candidate
                    continue

                save_result(experiment.id, result)
                new_corr = result.edit_correlation
                
                delta = new_corr - corr
                if method == ExperimentType.SimulatedAnnealingMin:
                    delta = -(delta)

                p = random.uniform(0.0, 1.0)
                
                if math.exp(delta/temperature) > p:
                    print("{0:3d} MOVE: {1:.4f}, {2:.4f} > {3:.4f}, temp: {4:.4f}, {5}".format(iteration, new_corr, math.exp(delta/temperature), p, temperature, new_candidate))
                    
                    candidate = new_candidate
                    corr = new_corr                
                else:
                    print("{0:3d} STAY: {1:.4f}, {2:.4f} <= {3:.4f}, temp: {4:.4f}, {5}".format(iteration, new_corr, math.exp(delta/temperature), p, temperature, new_candidate))

                if ((method == ExperimentType.SimulatedAnnealing and corr > best_corr) or
                   (method == ExperimentType.SimulatedAnnealingMin and corr < best_corr)):                    
                    best_corr = corr
                    best_candidate = candidate
                    best_iteration = iteration

                iteration += 1
                temperature = init_temp * (1 - iteration/time)
    
            print("Best candidate for {0} size {1} in iteration {2}: {3:.4f}, {4}".format(font.name, font_size, best_iteration, best_corr, best_candidate))
            
            experiment.end_time = datetime.now()
            experiment.save()

def default_systematicity(chars, fonts, font_sizes):
    for font in fonts:
        for font_size in font_sizes:
            with data.db.atomic():
                experiment_name = "Default: {0} size {1}.".format(font.name, font_size)
                experiment = Experiment(
                    name = experiment_name,
                    method = ExperimentType.DefaultSystematicity,
                    start_time = datetime.now(),
                    hyperparameters = None)
                experiment.save()
                print(experiment_name)

                renderer = shapes.GlyphRenderer(io.BytesIO(font.font_file))
                defaults = [axis.default for axis in renderer._axes]

                try:
                    result = systematicity.evaluate(chars, font, font_size, coords=None)
                except systematicity.FailedRenderException:
                    print("Unable to determine systematicity for {0} pt {1} because at least one glyph failed to render."
                        .format(font_size, font.name))
                    continue

                save_result(experiment.id, result)

                print("Corr: {0:.4f} for {1} pt {2}.".format(
                        result.edit_correlation, font_size, font.name))
                
                experiment.end_time = datetime.now()
                experiment.save()
            

"""
    Randomly alter the set of axis coordinates uniformly bounded by the 
    +/- percent of possible range defined by step_range.
"""
def alter_uniform(coords, axes, step_range):
    if step_range > 1 or step_range <= 0:
        raise Exception("Invalid step_range: {0}. Should be 0 < step_range <= 1.".format(step_range))

    new_coords = []
    
    for i in range(len(axes)):
        axis = axes[i]
        coord = coords[i]

        axis_range = axis.maximum - axis.minimum
        conv_range = (axis_range * step_range)
        
        while True:
            new_coord = round(coord + random.uniform(-conv_range, conv_range), 4)
            if new_coord >= axis.minimum and new_coord <= axis.maximum:
                break

        new_coords.append(new_coord)

    return new_coords

"""
    Randomly alter the set of axis coordinates within the applicable range
    using a Gaussian distribution having zero mean. The variance will be set
    to the portion of the axis range specified by var_range. For example, a
    var_range of 0.01 for axes with ranges of [20, 80, 100] will yield 
    variances of [0.2, 0.8, 1].
"""
def alter_gaussian(coords, axes, var_range):
    if var_range <= 0:
        raise Exception("Invalid var_range: {0}. var_range should be > 0"
            .format(var_range))
    if var_range > 1:
        raise Warning("Unusally high var_range of {0} will result in many "
                        "rejected alterations outside the axis range."
                        .format(var_range))
    new_coords = []
    
    for i in range(len(axes)):
        axis = axes[i]
        coord = coords[i]
        
        axis_range = axis.maximum - axis.minimum
        variance = axis_range * var_range
        
        while True:
            new_coord = round(coord + random.gauss(0, variance), 4)
            if new_coord >= axis.minimum and new_coord <= axis.maximum:
                break

        new_coords.append(new_coord)

    return new_coords

def save_result(experiment_id, systematicity_result):
    join = (ExperimentGlyphSet
            .select()
            .where(
                (ExperimentGlyphSet.experiment_id == experiment_id) &
                (ExperimentGlyphSet.glyph_set_id == systematicity_result.glyph_set_id))
            .first())

    # Don't duplicate if we're using cached result
    if join is not None:
        return

    join = ExperimentGlyphSet(experiment_id=experiment_id, glyph_set_id=systematicity_result.glyph_set_id)
    join.save()

if __name__ == "__main__":
    font = Font.select().where(Font.name == 'amstelvar-roman').first()
    renderer = shapes.GlyphRenderer(font.font_file)
