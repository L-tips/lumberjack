{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

    flake-parts.url = "github:hercules-ci/flake-parts";

    lumberjack-compiler = {
      url = "github:L-tips/lumberjack-compiler";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    inputs@{ flake-parts, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {

      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];

      perSystem =
        { pkgs, system, ... }:
        
        {
          devShells.default = pkgs.mkShell {
            nativeBuildInputs = with pkgs; [
              veryl # >= 0.20.2
              verilator
              uv
              surfer
              zlib
              yq-go

              inputs.lumberjack-compiler.packages.${system}.default
            ];
          };
        };
    };
}
