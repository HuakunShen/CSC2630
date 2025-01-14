#!/usr/bin/python
import sys
import time
import pickle
from typing import List

import numpy as np
import random
import cv2

from itertools import product
from math import cos, sin, pi, sqrt

from plotting_utils import draw_plan
from priority_queue import priority_dict

np.random.seed(1)


class State:
    """
    2D state.
    """

    def __init__(self, x, y, parent):
        """
        x represents the columns on the image and y represents the rows,
        Both are presumed to be integers
        """
        self.x = x
        self.y = y
        self.parent = parent
        self.children = []

    def __eq__(self, state):
        """
        When are two states equal?
        """
        return state and self.x == state.x and self.y == state.y

    def __hash__(self):
        """
        The hash function for this object. This is necessary to have when we
        want to use State objects as keys in dictionaries
        """
        return hash((self.x, self.y))

    def euclidean_distance(self, state):
        assert (state)
        return sqrt((state.x - self.x) ** 2 + (state.y - self.y) ** 2)


def steer_algorithm(s1: State, s2: State, height: int, max_radius: float):
    """
    This function is a helper function for steering

    Reason for this helper function: the algorithm is complicated and long, we need to avoid redundant code
    Problems:
    1. The coordinate system in python is different from that of the system of math
    (i.e. the direction of y is flipped),
    2. We expect to steer in all directions (360 degrees), while trig function arctan's range is [-pi/2, pi/2]
        quadrant 2 and 3 are not covered, we have to flip x-axis and do some trick
    """
    y1, y2 = height - s1.y, height - s2.y
    real_dy = s2.y - s1.y
    dx, dy = s2.x - s1.x, y2 - y1
    if dx == 0:
        # theta = np.arcsin(dy / max_radius)
        x, y = s1.x, y1 + -np.sign(real_dy) * max_radius
    else:
        # arctan's range is [-pi / 2, pi / 2] (i.e. +- 90 degrees),
        # quadrant 2 and 3 are not covered and impossible to steer towards that direction,
        # if dx is negative theta will be wrong, so we need to deal with negative dx separately
        theta = np.arctan(dy / dx)
        if dx < 0:
            # flip sign of dx to stay in [-pi / 2, pi / 2], result is theta2
            dx_flip = -dx
            theta = np.arctan(dy / dx_flip)
            theta = -np.pi - theta if dy < 0 else np.pi - theta
        dy2, dx2 = np.sin(theta) * max_radius, np.cos(theta) * max_radius
        x, y = int(s1.x + dx2), int(y1 + dy2)
    return x, int(height - y)


def debug_draw(img: np.ndarray, s: State):
    """This function is only for debugging purpose, to visualize the position of a state in map"""
    img[s.y - 3:s.y + 3, s.x - 3:s.x + 3] = np.array([0, 0, 255])
    cv2.imshow('image', img)
    cv2.waitKey(10)


class RRTPlanner:
    """
    Applies the RRT algorithm on a given grid world
    """

    def __init__(self, world):
        # (rows, cols, channels) array with values in {0,..., 255}
        self.world = world

        # (rows, cols) binary array. Cell is 1 iff it is occupied
        self.occ_grid = self.world[:, :, 0]
        self.occ_grid = (self.occ_grid == 0).astype('uint8')

    def state_is_free(self, state: State):
        """
        Does collision detection. Returns true iff the state and its nearby
        surroundings are free.
        """
        return (self.occ_grid[state.y - 5:state.y + 5, state.x - 5:state.x + 5] == 0).all()

    def sample_state(self):
        """
        Sample a new state uniformly randomly on the image.
        """
        # TODO: make sure you're not exceeding the row and columns bounds
        # x must be in {0, cols-1} and y must be in {0, rows -1}
        rows, cols = self.world.shape[:2]
        x = np.random.randint(0, cols)
        y = np.random.randint(0, rows)
        return State(x, y, None)

    def _follow_parent_pointers(self, state):
        """
        Returns the path [start_state, ..., destination_state] by following the
        parent pointers.
        """

        curr_ptr = state
        path = [state]

        while curr_ptr is not None:
            path.append(curr_ptr)
            curr_ptr = curr_ptr.parent

        # return a reverse copy of the path (so that first state is starting state)
        return path[::-1]

    def find_closest_state(self, tree_nodes: List[State], state: State):
        """From existing nodes, search for the node closest to the given state"""
        min_dist = float("Inf")
        closest_state = None
        for node in tree_nodes:
            dist = node.euclidean_distance(state)
            if dist < min_dist:
                closest_state = node
                min_dist = dist

        return closest_state

    def steer_towards(self, s_nearest: State, s_rand: State, max_radius: float):
        """
        Returns a new state s_new whose coordinates x and y
        are decided as follows:

        If s_rand is within a circle of max_radius from s_nearest
        then s_new.x = s_rand.x and s_new.y = s_rand.y

        Otherwise, s_rand is farther than max_radius from s_nearest.
        In this case we place s_new on the line from s_nearest to
        s_rand, at a distance of max_radius away from s_nearest.

        """

        # TODO: populate x and y properly according to the description above.
        # Note: x and y are integers and they should be in {0, ..., cols -1}
        # and {0, ..., rows -1} respectively
        if s_rand.euclidean_distance(s_nearest) <= max_radius:
            x, y = s_rand.x, s_rand.y
        else:
            x, y = steer_algorithm(s_nearest, s_rand, self.world.shape[0], max_radius)
            # dx, dy = s_rand.x - s_nearest.x, s_rand.y - s_nearest.y
            # if dx == 0:
            #     # theta = np.arcsin(dy / max_radius)
            #     x, y = s_nearest.x, s_nearest.y + np.sign(dy) * max_radius
            # else:
            #     theta = np.arctan(dy / dx)
            #     dy2, dx2 = np.sin(theta) * max_radius, np.cos(theta) * max_radius
            #     # print(dy2, dx2, theta, dy, dx, max_radius)
            #     x, y = int(s_nearest.x + dx2), int(s_nearest.y + dy2)
        s_new = State(x, y, s_nearest)
        return s_new

    def path_is_obstacle_free(self, s_from: State, s_to: State) -> bool:
        """
        Returns true iff the line path from s_from to s_to
        is free
        """
        assert (self.state_is_free(s_from))

        if not (self.state_is_free(s_to)):
            return False

        max_checks = 10
        for i in range(max_checks):
            # TODO: check if the inteprolated state that is float(i)/max_checks * dist(s_from, s_new)
            # away on the line from s_from to s_new is free or not. If not free return False
            distance = float(i) / max_checks * s_from.euclidean_distance(s_to)
            x, y = steer_algorithm(s_from, s_to, self.world.shape[0], distance)
            if not self.state_is_free(State(x, y, s_from)):
                return False

        # Otherwise the line is free, so return true
        return True

    def plan(self, start_state: State, dest_state: State, max_num_steps: int, max_steering_radius: float,
             dest_reached_radius: float):
        """
        Returns a path as a sequence of states [start_state, ..., dest_state]
        if dest_state is reachable from start_state. Otherwise, returns [start_state].
        Assume both source and destination are in free space.
        """
        assert (self.state_is_free(start_state))
        assert (self.state_is_free(dest_state))

        # The set containing the nodes of the tree
        tree_nodes = set()
        tree_nodes.add(start_state)

        # image to be used to display the tree
        img = np.copy(self.world)
        plan = [start_state]
        step_count = 0
        for step in range(max_num_steps):
            step_count += 1
            # TODO: Use the methods of this class as in the slides to compute s_new
            s_rand = self.sample_state()
            s_nearest = self.find_closest_state(list(tree_nodes), s_rand)
            s_new = self.steer_towards(s_nearest, s_rand, max_steering_radius)
            if self.path_is_obstacle_free(s_nearest, s_new):
                tree_nodes.add(s_new)
                s_nearest.children.append(s_new)

                # If we approach the destination within a few pixels
                # we're done. Return the path.
                if s_new.euclidean_distance(dest_state) < dest_reached_radius:
                    dest_state.parent = s_new
                    plan = self._follow_parent_pointers(dest_state)
                    break

                # plot the new node and edge
                cv2.circle(img, (s_new.x, s_new.y), 2, (0, 0, 0))
                cv2.line(img, (s_nearest.x, s_nearest.y), (s_new.x, s_new.y), (255, 0, 0))

            # Keep showing the image for a bit even
            # if we don't add a new node and edge
            cv2.imshow('image', img)
            cv2.waitKey(10)

        draw_plan(img, plan, bgr=(0, 0, 255), thickness=2)
        cv2.waitKey(0)
        return [start_state]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: rrt_planner.py occupancy_grid.pkl")
        sys.exit(1)

    pkl_file = open(sys.argv[1], 'rb')
    # world is a numpy array with dimensions (rows, cols, 3 color channels)
    world = pickle.load(pkl_file)
    pkl_file.close()

    rrt = RRTPlanner(world)

    start_state = State(10, 10, None)
    dest_state = State(500, 500, None)

    max_num_steps = 1000  # max number of nodes to be added to the tree
    max_steering_radius = 30  # pixels
    dest_reached_radius = 50  # pixels
    plan = rrt.plan(start_state,
                    dest_state,
                    max_num_steps,
                    max_steering_radius,
                    dest_reached_radius)
