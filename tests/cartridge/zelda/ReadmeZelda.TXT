These are little NES demos which, although they don't do much, took me
a long time to make.  Why?  Because it took a series of steps to make
it.  First of all, the US Zelda one took less time.  I had to load up
the game Zelda into Nesticle, and take a snapshot of the CHR patterns.
I then had to set up the colour palette, the attribute table, and (the
longest part) figure out where each pattern in the pattern table went
into the name table.  Then, I had to set up all 255 sprites (It's hard
to tell where they are; they're the foliage, the middle part of the
sword, the water, etc...)

That was not too bad.  The Japanese Zelda was really a pain in the @$$.
I don't have a ROM of Zelda, so I had to load it up in my Famicom, and
using that and a snapshot of the title screen, I 'cleaned up' the image
of all colour fringing and video noise, to reduce it to Zelda's  colour
palette.  Then, I had to remap strategically the graphics into the CHR
pattern of the ROM, and change the name table to reflect those changes.

To facilitate changing the graphics, I put the name table data into a
file called "Zelda*.map".  If you want to compile this demo for your-
self, you will need to edit the ROM, and replace everything from
"Beginning ... End" (Should be exactly 960 bytes) with the "Zelda*.map"
file.  The file "Zelda.att" is just the attribute table from Zelda,
which I've already coded into the asm source.

I hope you like it.  This demo, although I coded it _by the book_, may
behave differently on different NES emulators.  A _good_ NES emulator,
that is, one that behaves closest to a real NES, should have no problem
running this thing.

Chris Covell
ccovell@direct.ca
http://mypage.direct.ca/c/ccovell/
Powered by Amiga!
