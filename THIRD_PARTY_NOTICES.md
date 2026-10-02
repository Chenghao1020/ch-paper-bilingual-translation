# Bundled math converter

`scripts/vendor/latex2mathml` contains latex2mathml **3.78.0** by Ronie Martinez,
distributed under the MIT license. The original license is included at
`scripts/vendor/latex2mathml/LICENSE`.

Source: https://github.com/roniemartinez/latex2mathml

Release: https://pypi.org/project/latex2mathml/3.78.0/

Local modification: `__init__.py` sets the pinned version directly instead of
querying installed distribution metadata, allowing this vendored copy to work
without a separate installation. Other vendor source files are unchanged.

The converter runs locally when building the reader. Generated HTML embeds
native MathML and has no dependency on a hosted renderer or external fonts.
