#!/usr/bin/python3
"""Recipe creation tool - catkin support plugin."""

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
import logging

from html.parser import HTMLParser
from lxml import etree

from recipetool.create import RecipeHandler
from recipetool.create_buildsys import CmakeExtensionHandler

LOGGER = logging.getLogger('recipetool')

IS_CATKIN = False


class RosHTMLParser(HTMLParser):
    """ROS HTML Parser class.

    Primarily for removing any XHTML from the <description> tag.
    See: http://www.ros.org/reps/rep-0127.html#description (Format 1)
    See: http://www.ros.org/reps/rep-0140.html#description (Format 2)
    """

    basic_text = ""

    def handle_data(self, data):
        """Override HTMLParser handle_data method."""
        if len(self.basic_text) > 0:
            self.basic_text = self.basic_text + " "
        self.basic_text = self.basic_text + data.strip()


class RosXmlParser:
    """ROS package.xml Parser class.

    Uses the etree class from lxml to parse the ROS package.xml file.
    This file is main source for information for constructing the BitBake
    recipe for the ROS package.

    See: http://www.ros.org/reps/rep-0127.html (Format 1)
    See: http://www.ros.org/reps/rep-0140.html (Format 2)
    """

    package_format = 0

    def __init__(self, xml_path):
        """Initialize the class by finding the package format version."""
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
            LOGGER.warning("FORCING ROS Package Format to version " +
                           str(self.package_format))
        elif self.package_format < 1:
            self.package_format = 1
            LOGGER.warning("FORCING ROS Package Format to version " +
                           str(self.package_format))

        LOGGER.debug("ROS Package Format version " + str(self.package_format))

    def get_format(self):
        """Return the package.xml format version."""
        return str(self.package_format)

    def clean_string(self, raw_string):
        """Remove white space and sanitize the string.

        Replace double quotes with single quotes as bitbake
        recipes variables will be set with double quotes.
        """
        return re.sub(r'\s+', ' ', raw_string.strip().replace('"', "'"))

    def get_single(self, xpath, required=True):
        """Return a single string value for the given xpath."""
        xpath_list = self.tree.xpath(xpath)
        if len(xpath_list) < 1:
            if required:
                LOGGER.error("ROS package.xml missing element " + str(xpath))
                return None
        elif len(xpath_list) > 1:
            LOGGER.warning("ROS package.xml has more than 1 match for " +
                           str(xpath))

        return self.clean_string(xpath_list[0].text)

    def get_multiple(self, xpath, required=True):
        """Return a list of string values for the given xpath."""
        items = []
        xpath_list = self.tree.xpath(xpath)
        if len(xpath_list) < 1:
            if required:
                LOGGER.error("ROS package.xml missing element " + str(xpath))
        for item in xpath_list:
            items.append(self.clean_string(item.text))

        return items

    def get_multiple_with_email(self, xpath, required=True):
        """Return list of string values and email attrib for given xpath."""
        items = []
        xpath_list = self.tree.xpath(xpath + "[@email]")
        if len(xpath_list) < 1:
            if required:
                LOGGER.error("ROS package.xml missing element " + str(xpath))
        for item in xpath_list:
            fullstring = self.clean_string(item.text)
            email = self.clean_string(item.get('email'))
            if len(email) > 0:
                fullstring = fullstring + " <" + email + ">"
            items.append(fullstring)

        return items

    def get_name(self):
        """Return the Name of the ROS package."""
        return self.get_single("/package/name")

    def get_version(self):
        """Return the Version of the ROS package."""
        return self.get_single("/package/version")

    def get_description(self):
        """Return the Description of the ROS package.

        Remove the XHTML information, if present, and only return
        a simple text string description for the package.
        """
        parser = RosHTMLParser()
        parser.feed(self.get_single("/package/description"))
        return self.clean_string(parser.basic_text)

    def get_authors(self):
        """Return list of Authors of the ROS package."""
        return self.get_multiple_with_email("/package/author", required=False)

    def get_maintainers(self):
        """Return list of Maintainers of the ROS package."""
        return self.get_multiple_with_email("/package/maintainer")

    def get_licenses(self):
        """Return list of Licenses of the ROS package."""
        return self.get_multiple("/package/license")

    def get_dependencies(self):
        """Return list of package Dependencies of the ROS package."""
        dependencies = []
        for dependency in self.get_multiple("/package/build_depend"):
            dependencies.append(dependency.text.replace("_", "-"))
        return dependencies


class CatkinCmakeHandler(CmakeExtensionHandler):
    """Catkin handler extension for CMake build system."""

    def process_findpackage(self, srctree, fn, pkg, deps, outlines,
                            inherits, values):
        """Set global flag if this is catkin package.

        This is needed for the RecipeHandler to ensure we are processing
        a catkin build system recipe.
        """
        if pkg == 'catkin':
            global IS_CATKIN
            IS_CATKIN = True
            return True
        return False


class CatkinRecipeHandler(RecipeHandler):
    """Catkin handler extension for recipetool."""

    def process(self, srctree, classes, lines_before, lines_after, handled,
                extravalues):
        """Main processing function for Catkin recipe.

        We remove 'cmake' from the inherit and add in 'catkin'.
        Read the key tags from the package.xml ROS file and generate
        the corresponding recipe variables for the recipe file.
        """
        if not IS_CATKIN:
            # lines_after.append('# This is NOT a Catkin (ROS) based recipe')
            return False

        package_list = RecipeHandler.checkfiles(srctree, ['package.xml'])
        if len(package_list) > 0:
            for package_file in package_list:
                LOGGER.info("Found package_file: " + package_file)
                xml = RosXmlParser(package_file)
                # When building, we only want the catkin build class, not cmake
                # even though catkin is really cmake+python tooling
                classes.remove('cmake')
                classes.append('catkin')

                extravalues['PN'] = xml.get_name()  # Ignored if set
                extravalues['PV'] = xml.get_version()

                licenses = xml.get_licenses()
                if len(licenses) < 1:
                    LOGGER.error("package.xml missing reqired LICENSE field!")
                else:
                    lines_after.append("LICENSE = \"" +
                                       " & ".join(licenses) + "\"")
                    extravalues['LICENSE'] = " & ".join(licenses)

                lines_after.append('# This is a Catkin (ROS) based recipe')
                lines_after.append('# ROS package.xml format version ' +
                                   xml.get_format())
                lines_after.append('')

                lines_after.append("DESCRIPTION = \"" +
                                   xml.get_description() + "\"")

                authors = xml.get_authors()
                if len(authors) > 0:
                    lines_after.append("# ROS_AUTHOR = \"" +
                                       authors[0] + "\"")
                    del authors[0]
                    for author in authors:
                        lines_after.append("# ROS_AUTHOR += \"" +
                                           author + "\"")

                maintainers = xml.get_maintainers()
                if len(maintainers) > 0:
                    lines_after.append("# ROS_MAINTAINER = \"" +
                                       maintainers[0] + "\"")
                    del maintainers[0]
                    for maintainer in maintainers:
                        lines_after.append("# ROS_MAINTAINER += \"" +
                                           maintainer + "\"")

                lines_after.append("SECTION = \"devel\"")

            return True
        else:
            lines_after.append('### ERROR: ' +
                               'Catkin project missing required package.xml')
            LOGGER.error('Catkin project missing required package.xml')

        return False


def register_recipe_handlers(handlers):
    """Register our recipe handler in front of default cmake handler."""
    handlers.append((CatkinRecipeHandler(), 21))


def register_cmake_handlers(handlers):
    """Register our CMake extension handler."""
    handlers.append(CatkinCmakeHandler())
