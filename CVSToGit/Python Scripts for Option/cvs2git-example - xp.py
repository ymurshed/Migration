# The program that is run to convert from CVS to git is called
# cvs2git.  Run it with the --options option, passing it this file
# like this:
#
#     cvs2git --options=cvs2git-example.options
#
# The output of cvs2git is a blob file and a dump file that can be
# loaded into git using the "git fast-import" command. 

# Import some modules that are used in setting the options:
import os

from cvs2svn_lib import config
from cvs2svn_lib import changeset_database
from cvs2svn_lib.common import CVSTextDecoder
from cvs2svn_lib.log import logger
from cvs2svn_lib.git_revision_collector import GitRevisionCollector
from cvs2svn_lib.external_blob_generator import ExternalBlobGenerator
from cvs2svn_lib.git_output_option import GitRevisionMarkWriter
from cvs2svn_lib.git_output_option import GitOutputOption
from cvs2svn_lib.dvcs_common import KeywordHandlingPropertySetter
from cvs2svn_lib.rcs_revision_manager import RCSRevisionReader
from cvs2svn_lib.cvs_revision_manager import CVSRevisionReader
from cvs2svn_lib.symbol_strategy import AllBranchRule
from cvs2svn_lib.symbol_strategy import AllTagRule
from cvs2svn_lib.symbol_strategy import BranchIfCommitsRule
from cvs2svn_lib.symbol_strategy import ExcludeRegexpStrategyRule
from cvs2svn_lib.symbol_strategy import ForceBranchRegexpStrategyRule
from cvs2svn_lib.symbol_strategy import ForceTagRegexpStrategyRule
from cvs2svn_lib.symbol_strategy import ExcludeTrivialImportBranchRule
from cvs2svn_lib.symbol_strategy import ExcludeVendorBranchRule
from cvs2svn_lib.symbol_strategy import HeuristicStrategyRule
from cvs2svn_lib.symbol_strategy import UnambiguousUsageRule
from cvs2svn_lib.symbol_strategy import HeuristicPreferredParentRule
from cvs2svn_lib.symbol_strategy import SymbolHintsFileRule
from cvs2svn_lib.symbol_transform import ReplaceSubstringsSymbolTransform
from cvs2svn_lib.symbol_transform import RegexpSymbolTransform
from cvs2svn_lib.symbol_transform import IgnoreSymbolTransform
from cvs2svn_lib.symbol_transform import NormalizePathsSymbolTransform
from cvs2svn_lib.property_setters import AutoPropsPropertySetter
from cvs2svn_lib.property_setters import ConditionalPropertySetter
from cvs2svn_lib.property_setters import cvs_file_is_binary
from cvs2svn_lib.property_setters import CVSBinaryFileDefaultMimeTypeSetter
from cvs2svn_lib.property_setters import CVSBinaryFileEOLStyleSetter
from cvs2svn_lib.property_setters import DefaultEOLStyleSetter
from cvs2svn_lib.property_setters import EOLStyleFromMimeTypeSetter
from cvs2svn_lib.property_setters import ExecutablePropertySetter
from cvs2svn_lib.property_setters import KeywordsPropertySetter
from cvs2svn_lib.property_setters import MimeMapper
from cvs2svn_lib.property_setters import SVNBinaryFileKeywordsPropertySetter

# To choose the level of logging output, uncomment one of the
# following lines:
#logger.log_level = logger.WARN
#logger.log_level = logger.QUIET
logger.log_level = logger.NORMAL
#logger.log_level = logger.VERBOSE
#logger.log_level = logger.DEBUG


# The directory to use for temporary files:
ctx.tmpdir = r'cvs2git-tmp'

# During FilterSymbolsPass, cvs2git records the contents of file
# revisions into a "blob" file in git-fast-import format.
# This second alternative is vastly faster than the version above.  It
# uses an external Python program to reconstruct the contents of CVS
# file revisions and write it to the specified file.  If blob_filename
# is None, the blobs will be written to a temporary file then streamed
# to stdout in OutputPass:
ctx.revision_collector = ExternalBlobGenerator(
    blob_filename=os.path.join(ctx.tmpdir, 'git-blob.dat')
    )

ctx.revision_reader = None
ctx.trunk_only = False

# How to convert CVS author names, log messages, and filenames to Unicode.  
ctx.cvs_author_decoder = CVSTextDecoder(
        [
            'utf8',
            #'latin1',
            #'ascii',
        ],
        fallback_encoding='ascii'
    )
    
ctx.cvs_log_decoder = CVSTextDecoder(
        [
            'utf8',
            #'latin1',
            #'ascii',
        ],
        fallback_encoding='ascii',
        eol_fix='\n',
    )
    
# You might want to be especially strict when converting filenames to
# Unicode (e.g., maybe not specify a fallback_encoding).
ctx.cvs_filename_decoder = CVSTextDecoder(
        [
            'utf8',
            #'latin1',
            #'ascii',
        ],
        fallback_encoding='ascii'
    )

# Template for the commit message to be used for initial project commits.
ctx.initial_project_commit_message = (
    'Standard project directories initialized by cvs2git.'
    )

# Template for the commit message to be used for commits in which
# symbols are created.  This message can use '%(symbol_type)s' to
# include the type of the symbol ('branch' or 'tag') or
# '%(symbol_name)s' to include the name of the symbol.
ctx.symbol_commit_message = (
    "This commit was manufactured by cvs2git to create %(symbol_type)s "
    "'%(symbol_name)s'."
    )

# Template for the commit message to be used for commits in which
# tags are pseudo-merged back to their source branch.  This message can
# use '%(symbol_name)s' to include the name of the symbol.
# (Not used by default unless you enable tie_tag_fixup_branches on
# GitOutputOption.)
ctx.tie_tag_ancestry_message = (
    "This commit was manufactured by cvs2git to tie ancestry for "
    "tag '%(symbol_name)s' back to the source branch."
    )


# This option can be set to the name of a filename to which are stored
# statistics and conversion decisions about the CVS symbols.
ctx.symbol_info_filename = None
#ctx.symbol_info_filename = 'symbol-info.txt'

global_symbol_strategy_rules = [
    # To force all symbols matching a regular expression to be
    # converted as branches, add rules like the following:
    #ForceBranchRegexpStrategyRule(r'branch.*'),

    # To force all symbols matching a regular expression to be
    # converted as tags, add rules like the following:
    #ForceTagRegexpStrategyRule(r'tag.*'),

    # To force all symbols matching a regular expression to be
    # excluded from the conversion, add rules like the following:
    #ExcludeRegexpStrategyRule(r'dev|new_feature'),

    # Sometimes people use "cvs import" to get their own source code
    # into CVS.  This practice creates a vendor branch 1.1.1 and
    # imports the code onto the vendor branch as 1.1.1.1, then copies
    # the same content to the trunk as version 1.1.  Normally, such
    # vendor branches are useless and they complicate the SVN history
    # unnecessarily.  The following rule excludes any branches that
    # only existed as a vendor branch with a single import (leaving
    # only the 1.1 revision).  If you want to retain such branches,
    # comment out the following line.  (Please note that this rule
    # does not exclude vendor *tags*, as they are not so easy to
    # identify.)
    ExcludeTrivialImportBranchRule(),

    # To exclude all vendor branches (branches that had "cvs import"s
    # on them but no other kinds of commits), uncomment the following
    # line:
    #ExcludeVendorBranchRule(),

    # Usually you want this rule, to convert unambiguous symbols
    # (symbols that were only ever used as tags or only ever used as
    # branches in CVS) the same way they were used in CVS:
    UnambiguousUsageRule(),

    # If there was ever a commit on a symbol, then it cannot be
    # converted as a tag.  This rule causes all such symbols to be
    # converted as branches.  If you would like to resolve such
    # ambiguities manually, comment out the following line:
    BranchIfCommitsRule(),

    # Last in the list can be a catch-all rule that is used for
    # symbols that were not matched by any of the more specific rules above.  

    # Convert ambiguous symbols based on whether they were used more
    # often as branches or as tags:
    HeuristicStrategyRule(),

    # Convert all ambiguous symbols as branches:
    #AllBranchRule(),
    
    # Convert all ambiguous symbols as tags:
    #AllTagRule(),

    # The last rule is here to choose the preferred parent of branches
    # and tags, that is, the line of development from which the symbol
    # sprouts.
    HeuristicPreferredParentRule(),
    ]

# Specify a username to be used for commits for which CVS doesn't
# record the original author (for example, the creation of a branch).
ctx.username = 'cvs2git'

# ctx.file_property_setters and ctx.revision_property_setters contain
# rules used to set the svn properties on files in the converted archive.
ctx.file_property_setters.extend([
    # To read mime types from a file and use them to set svn:mime-type
    # based on the filename extensions, uncomment the following line
    # and specify a filename (see http://en.wikipedia.org/wiki/Mime.types for information about mime.types files):
    #MimeMapper(r'/etc/mime.types', ignore_case=False),

    # Omit the svn:eol-style property from any files that are listed
    # as binary (i.e., mode '-kb') in CVS:
    CVSBinaryFileEOLStyleSetter(),

    # If the file is binary and its svn:mime-type property is not yet
    # set, set svn:mime-type to 'application/octet-stream'.
    CVSBinaryFileDefaultMimeTypeSetter(),

    # To try to determine the eol-style from the mime type, uncomment the following line:
    #EOLStyleFromMimeTypeSetter(),

    #Other possible options: 'CRLF', 'CR', 'LF'.
    DefaultEOLStyleSetter(None),
    #DefaultEOLStyleSetter('native'),

    # Prevent svn:keywords from being set on files that have svn:eol-style unset.
    SVNBinaryFileKeywordsPropertySetter(),

    # If svn:keywords has not been set yet, set it based on the file's CVS mode:
    KeywordsPropertySetter(config.SVN_KEYWORDS_VALUE),

    # Set the svn:executable flag on any files that are marked in CVS as being executable:
    ExecutablePropertySetter(),

    # The following causes keywords to be untouched in binary files and collapsed in all text to be committed:
    ConditionalPropertySetter(
        cvs_file_is_binary, KeywordHandlingPropertySetter('untouched'),
        ),

    KeywordHandlingPropertySetter('collapsed'),
    ])

ctx.revision_property_setters.extend([
    ])

# To skip the cleanup of temporary files, uncomment the following option:
#ctx.skip_cleanup = True

# cvs2git only supports single-project conversions (multiple-project
# conversions wouldn't really make sense for git anyway).  
# So this option must be set to False:
ctx.cross_project_commits = False

# git itself doesn't allow commits that affect more than one branch,
# so this option must be set to False:
ctx.cross_branch_commits = False

# By default, the .cvsignore files are included in the conversion output.  
# If you would like to omit the .cvsignore files from the output, set this option to False:
ctx.keep_cvsignore = True

# By default, it is a fatal error for a CVS ",v" file to appear both
# inside and outside of an "Attic" subdirectory (this should never
# happen, but frequently occurs due to botched repository
# administration).  If you would like to retain both versions of such
# files, change the following option to True, and the attic version of
# the file will be written to a subdirectory called "Attic" in the
# output repository:
ctx.retain_conflicting_attic_files = False

# CVS uses unix login names as author names whereas git requires
# author names to be of the form "foo <bar>".  The default is to set
# the git author to "cvsauthor <cvsauthor>".  author_transforms can be
# used to map cvsauthor names (e.g., "jrandom") to a true name and
# email address (e.g., "J. Random <jrandom@example.com>" for the example shown).
author_transforms={
    'ymurshed' : 'Yaad Murshed <rifatyaad@gmail.com>',
    
    # This one will be used for commits for which CVS doesn't record the original author.
    'cvs2git' : 'cvs2git <admin@example.com>',
    }

# This is the main option that causes cvs2git to output to a
# "fastimport"-format dumpfile rather than to Subversion:
ctx.output_option = GitOutputOption(
    # The blobs will be written via the revision recorder, so in
    # OutputPass we only have to emit references to the blob marks:
    GitRevisionMarkWriter(),

    # The file in which to write the git-fast-import stream that
    # contains the changesets and branch/tag information, or None
    # to write it to stdout:
    dump_filename=os.path.join(ctx.tmpdir, 'git-dump.dat'),

    # Optional map from CVS author names to git author names:
    author_transforms=author_transforms,
    )

# Change this option to True to turn on profiling of cvs2git (for debugging purposes):
run_options.profiling = False

# Now set the project to be converted to git. cvs2git only supports
# single-project conversions, so this method must only be called once:
run_options.set_project(
    # The filesystem path to the part of the CVS repository (*not* a
    # CVS working copy) that should be converted.  This may be a
    # subdirectory (i.e., a module) within a larger CVS repository.
    r'D:\Work\cvsrepo\eresdev\eresdev',

    # A list of symbol transformations that can be used to rename
    # symbols in this project.
    symbol_transforms=[
        # Use IgnoreSymbolTransforms like the following to completely
        # ignore symbols matching a regular expression when parsing the CVS repository.
        # It is *not* recommended to use this instead of ExcludeRegexpStrategyRule; 
        #IgnoreSymbolTransform(r'nightly-build-tag-.*')

        # RegexpSymbolTransforms transform symbols textually using a
        # regular expression.  The first argument is a Python regular
        # expression pattern and the second is a replacement pattern.
        #RegexpSymbolTransform(r'release-(\d+)_(\d+)',
        #                      r'release-\1.\2'),
        #RegexpSymbolTransform(r'release-(\d+)_(\d+)_(\d+)',
        #                      r'release-\1.\2.\3'),

        # Simple 1:1 character replacements can also be done.  The
        # following transform, which converts backslashes into forward
        # slashes, should usually be included:
        ReplaceSubstringsSymbolTransform('\\','/'),

        # This last rule eliminates leading, trailing, and repeated slashes within the output symbol names:
        NormalizePathsSymbolTransform(),
        ],

    # See the definition of global_symbol_strategy_rules above for a
    # description of this option:
    symbol_strategy_rules=global_symbol_strategy_rules,

    # Exclude paths from the conversion. Should be relative to
    # repository path and use forward slashes:
    #exclude_paths=['file-to-exclude.txt,v', 'dir/to/exclude'],
    )