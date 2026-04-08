/agent-roles/software-architect-agent /agent-roles/implementation-agent/agent-roles/planning-agent

/use-all-mcp

thoroughly read the input document to this command. do the following in parallel:

1. thoroughly study and digest the state of all repos and subrepos
2. thoroughly understand the current state of progress in relation to the document.

then intensely prepare yourself to continue implementation, documentation, testing, verification, and validation towards complete and comprehensive execution of the document.

once you are prepared, start working.

create and update helpful mdc files and Cursor rules to develop towards the design invariants and contracts defined here: <http://development.sasankvishnubhatla.net/tcowmbh/task/sv0-compiler-vision-and-design.html> and all throughout sv0-toolchain and sv0doc.

make the necessary commits (without GPG signing, ensure that the commit messages are verbose, ensure that each commit is an atomic change) and tags, and then push all subrepos.

ensure all options are completed. ensure all documentation is updated and that the mcp server is updated.

ensure all timestamp updates are actually accurate to my current time and timezone.

ensure that all tests and the CI/CD pipelines are passing after every push. use the gh tool to check that all pipelines are passing. if any fail, fix them immediately and then continue development towards completing the document.

ensure that there are no hanging execution threads during your debugging.

when you must ask the user something, keep it **design-related or high-impact**; see `.cursor/rules/34-user-prompts-design-only.mdc`. otherwise proceed using the repo, tasks, and scripts.
