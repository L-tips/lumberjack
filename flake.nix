{
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];

      forAllSystems = nixpkgs.lib.genAttrs systems;
    in
    {
      devShells = forAllSystems (
        system:
        let
          pkgs = import nixpkgs {
            inherit system;
            # config.allowUnfree = true;
          };

          veryl = pkgs.veryl.overrideAttrs (
            old:
            let
              src = pkgs.fetchFromGitHub {
                owner = "veryl-lang";
                repo = "veryl";
                rev = "81daeab2bf4596016db472fec72219a0098b18be";
                hash = "sha256-TB8gmURTH6SQJCl3n00okGvlN/viAqITAUVJonscbFQ=";
              };
            in
            {
              inherit src;
              cargoDeps = pkgs.rustPlatform.fetchCargoVendor {
                inherit src;
                name = "veryl";
                hash = "sha256-/BKVUz3m26MvUvxp9Irtfd0RhbGVZPC2wnZ+Ow1evtU=";
              };
            }
          );
        in
        {
          default = pkgs.mkShell {
            nativeBuildInputs = with pkgs; [
              veryl
              verilator
              uv
              surfer
              # The verilator package is missing the zlib dependency
              zlib
            ];
          };
        }
      );
    };
}
