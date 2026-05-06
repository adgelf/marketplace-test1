# Claude Plugins Marketplace

This marketplace is where Mirantis teams share Claude Code plugins — packaged capabilities that extend what Claude Code can do.

---

## Claude Skills Marketplace for Engineering Teams at Mirantis

---

## Plugins and skills

Two terms you will see throughout this site:

**Plugin** — the installable package. A plugin is what this marketplace distributes, what you install with `/plugin install`, and what lives in a repository as a structured directory. A plugin can contain one or more skills, an MCP server, configuration, and documentation.

**Skill** — an individual `/command` within a plugin. When you type `/example-skill`, you are invoking a skill. Skills are defined by a prompt file (`SKILL.md`) inside the plugin and can optionally call tools exposed by an MCP server.

In practice, many plugins contain exactly one skill with the same name as the plugin itself. More capable plugins may bundle several related skills together.

---

## Prerequisites

You need **Claude Code** installed and running. If you haven't done that yet, ask IT — setup takes about five minutes and your Mirantis credentials are all you need.

---

## One-time setup

Add the Mirantis plugins marketplace to your Claude Code installation. Open a terminal, start Claude Code, and run:

```
/plugin marketplace add https://adgelf.github.io/marketplace-test1/marketplace.json
```

You only need to do this once. Claude Code will remember it.

---

## Browse available plugins

To see what's available:

```
/plugin list
```

---

## Install a plugin

```
/plugin install <plugin-name>@mirantis-plugins
```

Replace `<plugin-name>` with the name of the plugin you want. For example:

```
/plugin install example-skill@mirantis-plugins
```

---

## Use a skill

Once a plugin is installed, invoke its skill by typing `/` followed by the skill name:

```
/example-skill
```

Claude Code will run the skill in the context of whatever you're working on.

---

## Keep plugins up to date

When new plugins are added or existing ones are updated, refresh your local list:

```
/plugin marketplace update mplace1
```

Then reinstall any plugins you want to update.

---

<!--
## Plugin Dev Tools

If you are building a plugin, use the Plugin Dev Tools. These are fully-validated platform plugins that encode the standards and review criteria used by marketplace curators — so you can catch and fix problems before filing a PR, and submit with confidence.

| Tool | What it does |
|------|--------------|
| `/plugin-scaffold` | Generate a correct plugin structure from a description |
| `/plugin-docs-lint` | Check your README against documentation standards |
| `/plugin-security-check` | Deep inspection: compliance, security, blast radius, documentation quality |
| `/submit-plugin` | Full PR submission: runs the security check, clones the repo, files the PR |

Install any of them with:

```
/plugin install <tool-name>@mirantis-plugins
```

We encourage everyone building plugins to use these tools. The security check runs automatically as part of submission, and its report is included in every PR for reviewers.

---

## Contribute a plugin

Built something useful? Plugins in this marketplace are maintained in a shared repository. Use `/submit-plugin` to file a PR — the more we share, the less we each have to reinvent.

-->
