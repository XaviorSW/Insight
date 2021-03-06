from . import options_base
from .. import direct_message
import discord
from functools import partial
from sqlalchemy.orm import Session
import InsightExc


class Options_DM(options_base.Options_Base):
    def __init__(self, insight_channel):
        assert isinstance(insight_channel, direct_message.direct_message)
        super().__init__(insight_channel)

    def yield_options(self):
        yield (self.InsightOption_addToken, False)
        yield (self.InsightOption_deleteToken, False)
        yield (self.InsightOption_removeChannel, False)
        yield (self.InsightOption_syncnow, False)
        yield (self.InsightOption_viewtokens, False)
        yield from super().yield_options()

    def printout_my_tokens(self):
        db: Session = self.cfeed.service.get_session()
        return_str = "My Tokens:\n\n"
        try:
            for t in db.query(tb_tokens).filter(tb_tokens.discord_user == self.cfeed.user_id).all():
                return_str += t.str_wChcount() + '\n\n'
            return return_str
        except Exception as ex:
            print(ex)
            raise InsightExc.Db.DatabaseError
        finally:
            db.close()

    async def InsightOption_addToken(self, message_object: discord.Message):
        """Add new token - Add a new token for syncing contact information related to pilots, corporations, or alliances."""

        async def track_this(row_object, type_str):
            if row_object is not None:
                track = dOpt.mapper_return_yes_no(self.cfeed.discord_client, message_object)
                track.set_main_header(
                    "Sync standings for {} {} with this token?".format(type_str, row_object.get_name()))
                return await track()
            return False

        _options = dOpt.mapper_return_noOptions(self.cfeed.discord_client, message_object, timeout_seconds=400)
        _options.set_main_header(
            "Open this link and login to EVE's SSO system. After clicking 'Authorize' and being redirected to a blank webpage, copy the content of your browser "
            "address bar into this conversation: \n{}"
            "\n\nThe URL you paste should look similar to this:\n{}"
            .format(self.cfeed.service.sso.get_sso_login(), self.cfeed.service.sso.get_callback_example()))
        _options.set_footer_text("Please copy the URL into this conversation: ")
        auth_code = await _options()
        funct_call = partial(tb_tokens.generate_from_auth, self.cfeed.user_id, auth_code, self.cfeed.service)
        __resp = await self.cfeed.discord_client.loop.run_in_executor(None, funct_call)
        try:
            if not await track_this(__resp.object_pilot, "pilot"):
                __resp.character_id = None
            if not await track_this(__resp.object_corp, "corporation"):
                __resp.corporation_id = None
            if not await track_this(__resp.object_alliance, "alliance"):
                __resp.alliance_id = None
            await self.save_row(__resp)
            await self.reload(message_object)
            await self.InsightOption_syncnow(message_object)
        except Exception as ex:
            await self.cfeed.discord_client.loop.run_in_executor(None,
                                                                 partial(self.cfeed.service.sso.delete_token, __resp))
            raise ex

    async def InsightOption_deleteToken(self, message_object: discord.Message):
        """Delete token - Delete one of your added tokens and remove it from all channels."""
        def get_options():
            _options = dOpt.mapper_index_withAdditional(self.cfeed.discord_client, message_object)
            _options.set_main_header(
                "These are all the tokens currently in the system. Selecting a token will delete and remove it from all channels.")
            db: Session = self.cfeed.service.get_session()
            try:
                for token in db.query(tb_tokens).filter(tb_tokens.discord_user == self.cfeed.user_id).all():
                    _options.add_option(dOpt.option_returns_object(name=token.str_wChcount(), return_object=token))
                return _options
            except Exception as ex:
                print(ex)
                raise InsightExc.Db.DatabaseError
            finally:
                db.close()

        _options = await self.cfeed.discord_client.loop.run_in_executor(None, get_options)
        rm_token = await _options()
        await self.cfeed.discord_client.loop.run_in_executor(None,
                                                             partial(self.cfeed.service.sso.delete_token, rm_token))
        await self.reload(message_object)

    async def InsightOption_removeChannel(self, message_object: discord.Message):
        """Remove a token from Discord channel - Remove your token from a Discord channel."""
        def get_options():
            db: Session = self.cfeed.service.get_session()
            _options = dOpt.mapper_index_withAdditional(self.cfeed.discord_client, message_object)
            _options.set_main_header(
                "These are your tokens used by Discord channels. Select a channel to remove your token.")
            try:
                for t in db.query(tb_tokens).filter(tb_tokens.discord_user == self.cfeed.user_id).all():
                    if len(t.object_channels) > 0:
                        _options.add_header_row('Token ID: {}'.format(t.token_id))
                        for channel in t.object_channels:
                            cinfo = str(channel.channel_id)
                            try:
                                ch = self.cfeed.discord_client.get_channel(channel.channel_id)
                                if ch is not None:
                                    cname = ch.name
                                    sname = ch.guild.name
                                    cinfo = "{}({})".format(str(cname), str(sname))
                            except Exception as ex:
                                print(ex)
                            _options.add_option(dOpt.option_returns_object(name=cinfo, return_object=channel))
            except Exception as ex:
                print(ex)
                raise InsightExc.Db.DatabaseError
            finally:
                db.close()
            return _options

        options = await self.cfeed.discord_client.loop.run_in_executor(None, get_options)
        row = await options()
        await self.delete_row(row)
        await self.reload(message_object)

    async def InsightOption_syncnow(self, message_object: discord.Message):
        """Force sync - Force an API pull on all of your tokens. Note: Insight automatically syncs your tokens every 6 hours."""
        await message_object.channel.send("Syncing your tokens now")
        await self.cfeed.discord_client.loop.run_in_executor(None, partial(tb_tokens.sync_all_tokens,
                                                                           self.cfeed.user_id, self.cfeed.service))
        await self.InsightOption_viewtokens(message_object)

    async def InsightOption_viewtokens(self, message_object: discord.Message):
        """View my tokens - View information on all tokens you have with Insight."""
        resp = await self.cfeed.discord_client.loop.run_in_executor(None, self.printout_my_tokens)
        await message_object.channel.send("{}\n{}".format(message_object.author.mention, resp))

    async def InsightOptionAbstract_addchannel(self):
        message_object = await self.cfeed.channel_discord_object.send(
            "This tool will assist in adding a token to a channel")
        message_object.author = self.cfeed.discord_client.get_user(self.cfeed.user_id)

        def make_options():
            _options = dOpt.mapper_index_withAdditional(self.cfeed.discord_client, message_object)
            _options.set_main_header(
                "Select one of your tokens to add to the feed. If you do not have any tokens created yet, select the 'cancel' option"
                " and do the following:\n\nStep 1. Direct Message this bot with the command '!sync'.\n\nStep 2. Select the option"
                " to add a new token.\n\nStep 3. Follow the steps needed to add a token and then rerun the command '!sync' "
                "in the channel you wish to sync your contacts with.")
            db: Session = self.cfeed.service.get_session()
            try:
                _options.add_header_row("Your available tokens")
                for token in db.query(tb_tokens).filter(tb_tokens.discord_user == self.cfeed.user_id).all():
                    _options.add_option(dOpt.option_returns_object(name=token.str_wChcount(), return_object=token))
                return _options
            except Exception as ex:
                print(ex)
                raise InsightExc.Db.DatabaseError
            finally:
                db.close()

        options = await self.cfeed.discord_client.loop.run_in_executor(None, partial(make_options))
        return await options()


from discord_bot import discord_options as dOpt
from database.db_tables import *
