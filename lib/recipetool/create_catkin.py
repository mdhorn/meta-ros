# Recipe creation tool - catkin support plugin
#
# Copyright (C) 2017 Intel Corporation
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import re
import os
import logging

# from lxml import etree

from recipetool.create import RecipeHandler
from recipetool.create_buildsys import CmakeExtensionHandler

logger = logging.getLogger('recipetool')

isCatkin = False


class CatkinCmakeHandler(CmakeExtensionHandler):
    def process_findpackage(self, srctree, fn, pkg, deps, outlines, inherits, values):
        if pkg == 'catkin':
            global isCatkin
            isCatkin = True
            return True
        return False


class CatkinRecipeHandler(RecipeHandler):
    def process(self, srctree, classes, lines_before, lines_after, handled, extravalues):
        if not isCatkin:
            # lines_after.append('# This is NOT a Catkin (ROS) based recipe')
            return False

        if RecipeHandler.checkfiles(srctree, ['package.xml']):
            # When building, we only want the catkin build class, not cmake
            # even though catkin is really cmake+python tooling
            classes.remove('cmake')
            classes.append('catkin')

            lines_after.append('# This is a Catkin (ROS) based recipe')
            lines_after.append('')

            return True
        else:
            lines_after.append('### ERROR: Catkin project missing required package.xml')
            logger.error('Catkin project missing required package.xml')

        return False


def register_recipe_handlers(handlers):
    # Insert handler in front of default cmake handler
    handlers.append((CatkinRecipeHandler(), 21))

def register_cmake_handlers(handlers):
    handlers.append(CatkinCmakeHandler())


