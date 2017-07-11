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

from lxml import etree
from html.parser import HTMLParser

from recipetool.create import RecipeHandler
from recipetool.create_buildsys import CmakeExtensionHandler

logger = logging.getLogger('recipetool')

isCatkin = False


class rosHTMLParser(HTMLParser):
    basic_text = ""

    def handle_data(self, data):
        if len(self.basic_text) > 0:
            self.basic_text = self.basic_text + " "
        self.basic_text = self.basic_text + data.strip()

class rosXmlParser:

    package_format = 0

    def __init__(self, xml_path):
        # Default to ROS package format 1
        # http://wiki.ros.org/catkin/package.xml#Format_1_.28Legacy.29
        self.package_format = 1

        self.xml_path = xml_path
        self.tree = etree.parse(self.xml_path)
        # Check the ROS package format
        # http://wiki.ros.org/catkin/package.xml#Format_1_.28Legacy.29
        # or
        # http://wiki.ros.org/catkin/package.xml#Format_2_.28Recommended.29
        package_format_list = self.tree.xpath("/package[@format]")
        for pkg_format in package_format_list:
            self.package_format = int(pkg_format.get('format'))
        if self.package_format > 2:
            self.package_format = 2
            logger.warning("FORCING ROS Package Format to version " + str(self.package_format))
        elif self.package_format < 1:
            self.package_format = 1
            logger.warning("FORCING ROS Package Format to version " + str(self.package_format))

        logger.debug("ROS Package Format version " + str(self.package_format))

    def getFormat(self):
        return str(self.package_format)

    def cleanString(self, raw_string):
        # remove white space
        # replace double quotes with single quotes as bitbake
        # recipes variables will be set with double quotes.
        return raw_string.strip().replace('"', "'")

    def getSingle(self, xpath, required=True):
        xpath_list = self.tree.xpath(xpath)
        if len(xpath_list) < 1:
            if required:
                logger.error("ROS package.xml missing element " + str(xpath))
                return None
        elif len(xpath_list) > 1:
            logger.warning("ROS package.xml has more than 1 match for " + str(xpath))

        return self.cleanString(xpath_list[0].text)

    def getMultiple(self, xpath, requied=True):
        items = []
        xpath_list = self.tree.xpath(xpath)
        if len(xpath_list) < 1:
            if required:
                logger.error("ROS package.xml missing element " + str(xpath))
        for item in xpath_list:
            items.append(self.cleanString(item.text))

        return items

    def getMultipleWithEmail(self, xpath, required=True):
        items = []
        xpath_list = self.tree.xpath(xpath + "[@email]")
        if len(xpath_list) < 1:
            if required:
                logger.error("ROS package.xml missing element " + str(xpath))
        for item in xpath_list:
            fullstring = self.cleanString(item.text)
            email = self.cleanString(item.get('email'))
            if len(email) > 0:
                fullstring = fullstring + " <" + email + ">"
            items.append(fullstring)

        return items

    def getName(self):
        return self.getSingle("/package/name")

    def getVersion(self):
        return self.getSingle("/package/version")

    # Sometimes the description has
    def getDescription(self):
        parser = rosHTMLParser()
        parser.feed(self.getSingle("/package/description"))
        return parser.basic_text

    def getAuthors(self):
        return self.getMultipleWithEmail("/package/author", required=False)

    def getMaintainers(self):
        return self.getMultipleWithEmail("/package/maintainer")

    def getLicenses(self):
        return self.getMultiple("/package/license")

    def getDependencies(self):
        dependencies = []
        for dependency in self.tree.xpath("/package/build_depend"):
            dependencies.append(dependency.text.replace("_", "-"))
        return dependencies

    def getLicenseLineNumber(self):
        with open(self.xml_path) as file:
            for num, line in enumerate(file, 1):
                if 'license' in line:
                    return num
            return 'CLOSED'


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

        package_list = RecipeHandler.checkfiles(srctree, ['package.xml'])
        if len(package_list) > 0:
            for package_file in package_list:
                logger.info("Found package_file: " + package_file)
                xml = rosXmlParser(package_file)
                # When building, we only want the catkin build class, not cmake
                # even though catkin is really cmake+python tooling
                classes.remove('cmake')
                classes.append('catkin')

                extravalues['PN'] = xml.getName()
                extravalues['PV'] = xml.getVersion()

                licenses = xml.getLicenses()
                if len(licenses) < 1:
                    logger.error("package.xml missing reqired LICENSE field!")
                else:
                    lines_after.append("LICENSE = \"" + " & ".join(licenses) + "\"")
                    extravalues['LICENSE'] = " & ".join(licenses)

                lines_after.append('# This is a Catkin (ROS) based recipe')
                lines_after.append('# ROS package.xml format version ' + xml.getFormat())
                lines_after.append('')

                lines_after.append("DESCRIPTION = \"" + xml.getDescription() + "\"")

                authors = xml.getAuthors()
                if len(authors) > 0:
                    lines_after.append("# ROS_AUTHOR = \"" + authors[0] + "\"")
                    del authors[0]
                    for author in authors:
                        lines_after.append("# ROS_AUTHOR += \"" + author + "\"")

                maintainers = xml.getMaintainers()
                if len(maintainers) > 0:
                    lines_after.append("# ROS_MAINTAINER = \"" + maintainers[0] + "\"")
                    del maintainers[0]
                    for maintainer in maintainers:
                        lines_after.append("# ROS_MAINTAINER += \"" + maintainer + "\"")

                lines_after.append("SECTION = \"devel\"")

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


