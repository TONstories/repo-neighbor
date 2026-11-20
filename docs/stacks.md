# Find the project's verification command

| Stack | Evidence to inspect in the affected directory | Verification recipe |
| --- | --- | --- |
| Python | pyproject.toml, tox.ini, CI matrix, lockfile | Use the documented environment. Run the specific pytest or unittest target, then the required suite. |
| JavaScript / TypeScript | closest package.json, workspace declaration, lockfile, tsconfig | Read scripts and use the pinned package manager. Run the package's tests and type check when declared. |
| Go | nearest go.mod, go.work, CI build tags | Run the affected package tests with the tags CI uses. Use go test ./... when the project specifies it. |
| Rust | workspace Cargo.toml, feature flags, Cargo.lock | Run the affected crate tests with the feature set used by CI. |
| Java / Kotlin | Gradle wrapper, settings file, Maven wrapper or pom.xml | Use the repository wrapper, target module and CI's JDK. Check Android SDK and emulator needs before committing to a session. |
| C# / .NET | solution, csproj, global.json, target frameworks | Use the declared SDK; run dotnet test on the affected test project with CI's framework configuration. |
| Julia | Project.toml, Manifest.toml, test/runtests.jl | Follow the project environment and its documented Pkg.test target. |
| Haskell | cabal.project, package .cabal file, stack.yaml | Use the test suite and Cabal or Stack version used in CI. |
| Clojure | deps.edn, project.clj, test aliases | Read the actual alias or Leiningen test target in CI. |
| Fortran | fpm.toml, compiler flags in CI | Match the project compiler and run the documented fpm test target. |
| Ruby | Gemfile, Rakefile | Follow bundle exec rake test or the documented RSpec target. |
| PHP | composer.json | Inspect Composer scripts and run the affected PHPUnit suite. |
| Swift | Package.swift | Use the documented Swift toolchain and scoped swift test target. |
| Dart | pubspec.yaml | Choose dart test or flutter test according to the affected package. |
| Elixir | mix.exs | Run the relevant mix test file or umbrella app tests. |
| Scala | build.sbt | Run the documented sbt project and testOnly scope. |
| Zig | build.zig | Verify the compiler version and project test step. |
| C / C++ | Meson or CMake files | Inspect the CI compiler, configure a separate build directory and run the target suite. |

A recommendation identifies commands found in contribution docs or package scripts. When no command is found, inspect CI and the nearest manifest. Set aside environment setup time. Read scripts before executing them, especially when checking an unfamiliar repository.
