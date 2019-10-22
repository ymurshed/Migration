import os
import csv

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

# Constants
temp_dir = r'cvs2git-tmp'
temp_user_name = 'cvs2git'
git_blob_file = 'git-blob.dat'
git_dump_file = 'git-dump.dat'
author_mapping_file = 'author-mapping.txt'
project_mapping_file = 'project-mapping.txt' 


logger.log_level = logger.NORMAL

# The directory to use for temporary files:
ctx.tmpdir = temp_dir

ctx.revision_collector = ExternalBlobGenerator(
    blob_filename = os.path.join(ctx.tmpdir, git_blob_file)
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
    fallback_encoding = 'utf8'
)
    
ctx.cvs_log_decoder = CVSTextDecoder(
    [
        'utf8',
        #'latin1',
        #'ascii',
    ],
    fallback_encoding = 'utf8',
    eol_fix='\n'
)
    
ctx.cvs_filename_decoder = CVSTextDecoder(
    [
        'utf8',
        #'latin1',
        #'ascii',
    ],
    fallback_encoding = 'utf8'
)

ctx.initial_project_commit_message = (
    'Standard project directories initialized by cvs2git.'
)

ctx.symbol_commit_message = (
    "This commit was manufactured by cvs2git to create %(symbol_type)s "
    "'%(symbol_name)s'."
)

ctx.tie_tag_ancestry_message = (
    "This commit was manufactured by cvs2git to tie ancestry for "
    "tag '%(symbol_name)s' back to the source branch."
)

ctx.symbol_info_filename = None

global_symbol_strategy_rules = [
    ExcludeTrivialImportBranchRule(),
    UnambiguousUsageRule(),
    BranchIfCommitsRule(),
    HeuristicStrategyRule(),
    HeuristicPreferredParentRule()
]

ctx.username = temp_user_name

ctx.file_property_setters.extend(
    [
        CVSBinaryFileEOLStyleSetter(),
        CVSBinaryFileDefaultMimeTypeSetter(),
        DefaultEOLStyleSetter(None),
        SVNBinaryFileKeywordsPropertySetter(),
        KeywordsPropertySetter(config.SVN_KEYWORDS_VALUE),
        ExecutablePropertySetter(),
        ConditionalPropertySetter(cvs_file_is_binary, KeywordHandlingPropertySetter('untouched')),
        KeywordHandlingPropertySetter('collapsed'),
    ]
)

ctx.revision_property_setters.extend([])

ctx.cross_project_commits = False
ctx.cross_branch_commits = False
ctx.keep_cvsignore = True
ctx.retain_conflicting_attic_files = False


# Load author mapping from file
author_transforms = {}
csv_reader = csv.reader(open(author_mapping_file, "rb")) 
for row in csv_reader:
    cvs_author = row[0].strip()
    bitbucket_author = row[1].strip()

    if cvs_author not in author_transforms:
        author_transforms[cvs_author] = bitbucket_author
        print ('cvs author = [' + cvs_author + '] mapped to bitbucket author = [' + bitbucket_author + ']')


# This is the main option that causes cvs2git to output to a "fastimport"-format dumpfile rather than to Subversion:
ctx.output_option = GitOutputOption(
    GitRevisionMarkWriter(),
    dump_filename = os.path.join(ctx.tmpdir, git_dump_file),
    author_transforms = author_transforms,
)

# Change this option to True to turn on profiling of cvs2git (for debugging purposes):
run_options.profiling = False

# Single-project conversions, so this method must only be called once:
run_options.set_project(
    r'D:\Work\cvsrepo\eresdev\eresdev',

    symbol_transforms = [
        ReplaceSubstringsSymbolTransform('\\','/'),
        NormalizePathsSymbolTransform(),
    ],

    symbol_strategy_rules = global_symbol_strategy_rules
)