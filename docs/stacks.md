# Find the project's verification command

| Stack | Evidence to inspect in the affected directory | Verification recipe |
| --- | --- | --- |
| Python | pyproject.toml, tox.ini, CI matrix, lockfile | Use the documented environment. Run the specific pytest or unittest target, then the required suite. |
| JavaScript / TypeScript | closest package.json, workspace declaration, lockfile, tsconfig | Read scripts and use the pinned package manager. Run the package's tests and type check when declared. |
| Go | nearest go.mod, go.work, CI build tags | Run the affected package tests with the tags CI uses. Use go test ./... when the project specifies it. |
| Rust | workspace Cargo.toml, feature flags, Cargo.lock | Run the affected crate tests with the feature set used by CI. |
| Java / Kotlin | Gradle wrapper, settings file, Maven wrapper or pom.xml | Use the repository wrapper, target module and CI's JDK. Check Android SDK and emulator needs before committing to a session. |
| C# / .NET | solution, csproj, global.json, target frameworks | Use the declared SDK; run dotnet test on the affected test project with CI's framework configuration. |

A recommendation identifies commands found in contribution docs or package scripts. When no command is found, inspect CI and the nearest manifest. Set aside environment setup time. Read scripts before executing them, especially when checking an unfamiliar repository.
