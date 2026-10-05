"""Quick tour of the imho Python client (pip install imho).

Makes 5 requests to https://imho.run. Run: python examples/python_quickstart.py
"""

from imho import ImhoClient


def main() -> None:
    with ImhoClient() as imho:
        print("Games like Hollow Knight:")
        for game in imho.games_like("Hollow Knight", n=3)["results"]:
            print(f"  {game['rank']}. {game['name']} - {game['why']} ({game['price']['text']})")

        print("\nFor Stardew Valley + Terraria fans, co-op, no PvP, cozy farming:")
        recs = imho.recommend(
            ["Stardew Valley", "Terraria"],
            n=3,
            coop=True,
            exclude=["pvp"],
            preferences="cozy farming, no horror",
        )
        for game in recs["results"]:
            print(f"  {game['rank']}. {game['name']} - {game['why']}")
        print(f"  (read as tags: {recs['preferences']})")

        print("\nTrending on Steam:")
        trending = imho.trending(n=3)
        if trending["status"] == "collecting":
            print("  (still collecting data)")
        for game in trending["results"]:
            print(f"  {game['name']}: {game.get('reviews_week')} reviews this week")

        print("\nNew releases:")
        for game in imho.new_releases(n=3)["results"]:
            print(f"  {game['name']} ({game.get('release_date')})")

        print("\nSearch 'hollow kn':")
        for hit in imho.search_games("hollow kn", n=3)["results"]:
            print(f"  {hit['name']} ({hit['appid']}, {hit.get('year')})")

        print(f"\n{recs['attribution']}")


if __name__ == "__main__":
    main()
